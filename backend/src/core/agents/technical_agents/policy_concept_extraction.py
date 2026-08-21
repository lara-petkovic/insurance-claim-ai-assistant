import re
from typing import Any

from core.agents.base import AgentContext, BaseAgent
from core.agents.technical_agents.policy_polarity import clause_polarity, policy_clauses
from core.agents.technical_agents.shared import _merge_dict_lists_by_key
from core.claim_validation import extract_policy_period, policy_domain_metadata
from core.models.agent import AgentResponse
from core.models.analysis import (
    ClauseType,
    PolicyDocument,
    PolicyExtractionFindings,
    PolicyExtractionModelOutput,
)
from core.provenance import policy_clause
from models.model_client import get_model_client
from security.input_security import UNTRUSTED_INPUT_SYSTEM_RULE, untrusted_block


class PolicyConceptExtractionAgent(BaseAgent):
    """Extracts normalized coverage, exclusion, and policy-condition concepts."""

    name = "PolicyConceptExtractionAgent"

    COVERAGE_PATTERNS = {
        "fire_damage": ["fire", "smoke", "explosion", "lightning"],
        "storm_damage": ["storm", "flood", "weather"],
        "theft": ["theft", "attempted theft", "stolen", "forcible"],
        "water_damage": ["escape of water", "water installation", "pipe", "leak", "washing machine"],
        "broken_glass": ["breakage", "fixed glass", "sanitary ware", "glass"],
        "vehicle_damage": ["vehicle", "car", "collision", "accidental damage", "comprehensive"],
        "medical": ["medical", "hospital", "emergency treatment", "doctor", "illness"],
        "baggage_loss": ["baggage", "luggage", "personal belongings", "lost luggage"],
        "trip_cancellation": ["trip cancellation", "cancellation", "curtailment", "covered reason"],
    }

    EXCLUSION_PATTERNS = {
        "unoccupied_home": ["unoccupied", "unfurnished"],
        "gradual_damage": ["gradual", "repeated exposure", "long-term", "wear and tear"],
        "rot": ["rot"],
        "poor_maintenance": ["poor maintenance", "lack of maintenance"],
        "pipe_or_apparatus_itself": ["apparatus", "pipes from which the water escaped"],
        "subsidence_landslip": ["subsidence", "landslip", "ground heave"],
        "mechanical_breakdown": ["mechanical breakdown", "wear and tear"],
        "unattended_baggage": ["unattended baggage", "left unattended"],
        "pre_existing_medical": ["pre-existing", "pre existing", "known medical condition"],
    }

    def run(self, context: AgentContext) -> AgentResponse:
        policy_text = context.memory.get("DocumentIngestionAgent", {}).get("policy_text", "")
        lower = policy_text.lower()

        coverage_clauses = self._coverage_clauses(policy_text)
        covered_events = [
            {
                "concept": item["concept"],
                "matched_terms": item["matched_terms"],
                "evidence_text": item["evidence_text"],
                "polarity": item["polarity"],
                "direct_match": item["direct_match"],
            }
            for item in coverage_clauses
            if item["polarity"] == "covered"
        ]
        exclusions = self._exclusion_clauses(policy_text)

        required_documents = ["claim description", "damage photos"]
        if "repair estimate" in lower or "invoice" in lower:
            required_documents.append("repair estimate or invoice")
        if "police report" in lower:
            required_documents.append("police report for theft")
        if "weather" in lower:
            required_documents.append("weather evidence for storm claims")

        domain_metadata = policy_domain_metadata(context.request.insurance_type, policy_text)
        policy_period = extract_policy_period(policy_text)

        findings = {
            "policy_type": domain_metadata["policy_type"],
            "policy_period": policy_period,
            "insured_subject": domain_metadata["insured_subject"],
            "covered_events": covered_events,
            "coverage_clauses": coverage_clauses,
            "exclusions": exclusions,
            "limits": [],
            "deductible_or_excess": "excess mentioned in policy wording" if "excess" in lower else None,
            "required_claim_documents": required_documents,
            "special_conditions": ["policy wording structure normalized into shared concept schema"],
        }
        fallback = findings
        model_client = get_model_client()
        model_result = model_client.json_response(
            system=(
                "You are an insurance policy concept extraction agent. "
                "Return only valid JSON. Normalize heterogeneous policy wording into a shared insurance schema. "
                "Every model-added covered event or exclusion must include an exact evidence_text copied from the policy. "
                + UNTRUSTED_INPUT_SYSTEM_RULE
            ),
            prompt=(
                "Extract normalized insurance policy concepts from this policy text. "
                "Use this exact top-level JSON shape: "
                "{policy_type, policy_period, insured_subject, covered_events, exclusions, limits, "
                "deductible_or_excess, required_claim_documents, special_conditions}. "
                "covered_events and exclusions must be arrays of objects with at least concept and evidence_text.\n\n"
                f"SELECTED INSURANCE DOMAIN: {context.request.insurance_type.value}\n"
                f"POLICY TEXT:\n{untrusted_block('policy_text', policy_text, max_chars=12000)}"
            ),
            fallback=fallback,
            schema_name="policy_concept_extraction",
            response_model=PolicyExtractionModelOutput,
            schema_description="Normalized policy concepts with exact supporting policy text.",
        )
        findings_data: dict[str, Any] = {
            **fallback,
            **model_result.data,
            # Domain and dates are request/policy facts and must remain deterministic.
            "policy_type": fallback["policy_type"],
            "policy_period": fallback["policy_period"],
            "insured_subject": fallback["insured_subject"],
            "model_used": model_result.used_model,
        }
        verified_model_covered = self._verified_items(
            model_result.data.get("covered_events"), policy_text, required_polarity="covered"
        )
        verified_model_exclusions = self._verified_items(model_result.data.get("exclusions"), policy_text)
        findings_data["covered_events"] = _merge_dict_lists_by_key(
            covered_events,
            verified_model_covered,
        )
        findings_data["exclusions"] = _merge_dict_lists_by_key(
            exclusions,
            verified_model_exclusions,
        )
        raw_clauses = self._merge_coverage_clauses(
            coverage_clauses,
            [
                {
                    **item,
                    "polarity": clause_polarity(str(item["evidence_text"])),
                    "matched_terms": [],
                }
                for item in verified_model_covered
            ],
        )
        source_document = context.request.policy_document or PolicyDocument(
            filename=context.request.policy_filename or "policy",
            text=policy_text,
        )
        findings_data["coverage_clauses"] = [
            policy_clause(source_document, item)
            for item in raw_clauses
            if str(item.get("polarity")) == "covered"
        ]
        # Exclusion concepts with exact model evidence are also represented as typed clauses.
        typed_exclusions = [
            policy_clause(source_document, item, clause_type=ClauseType.EXCLUSION)
            for item in raw_clauses
            if str(item.get("polarity")) == "excluded"
        ] + [
            policy_clause(
                source_document,
                {**item, "polarity": "excluded"},
                clause_type=ClauseType.EXCLUSION,
            )
            for item in findings_data["exclusions"]
            if str(item.get("evidence_text", "")).strip()
        ]
        typed_conditions = [
            policy_clause(source_document, item, clause_type=ClauseType.CONDITION)
            for item in raw_clauses
            if str(item.get("polarity")) == "conditional"
        ]
        structural_clauses = self._structural_clauses(source_document, policy_text)
        typed_conditions.extend(structural_clauses[ClauseType.CONDITION])
        typed_limits = structural_clauses[ClauseType.LIMIT]
        typed_definitions = structural_clauses[ClauseType.DEFINITION]
        represented_text = {
            str(item.get("evidence_text", "")).strip().casefold() for item in raw_clauses
        }
        generic_operative_clauses = []
        for evidence_text in policy_clauses(policy_text):
            polarity = clause_polarity(evidence_text)
            if polarity not in {"covered", "excluded"} or evidence_text.strip().casefold() in represented_text:
                continue
            generic_operative_clauses.append(
                policy_clause(
                    source_document,
                    {
                        "concept": "general",
                        "evidence_text": evidence_text,
                        "polarity": polarity,
                        "direct_match": True,
                    },
                )
            )
        all_policy_clauses = self._deduplicate_typed_clauses(
            [
                *findings_data["coverage_clauses"],
                *typed_exclusions,
                *typed_conditions,
                *typed_limits,
                *typed_definitions,
                *generic_operative_clauses,
            ]
        )
        findings_data["coverage_clauses"] = [
            item for item in all_policy_clauses if item.clause_type is ClauseType.COVERAGE
        ]
        findings_data["exclusion_clauses"] = [
            item for item in all_policy_clauses if item.clause_type is ClauseType.EXCLUSION
        ]
        findings_data["condition_clauses"] = [
            item for item in all_policy_clauses if item.clause_type is ClauseType.CONDITION
        ]
        findings_data["limit_clauses"] = [
            item for item in all_policy_clauses if item.clause_type is ClauseType.LIMIT
        ]
        findings_data["definition_clauses"] = [
            item for item in all_policy_clauses if item.clause_type is ClauseType.DEFINITION
        ]
        findings_data["policy_clauses"] = all_policy_clauses
        findings = PolicyExtractionFindings.model_validate(findings_data)
        return self.respond(
            findings=findings,
            confidence=0.78 if covered_events else 0.45,
            warnings=(
                ["Used configured model for policy concept extraction."]
                if model_result.used_model
                else ([] if covered_events else ["No covered events were confidently extracted."])
            ),
            requires_human_review=not bool(covered_events),
            messages=[
                self.message(
                    f"Normalized {len(findings.get('covered_events', []))} covered event(s) and {len(findings.get('exclusions', []))} exclusion concept(s).",
                    to_agent="CoverageMatchingAgent",
                    message_type="handoff",
                    metadata={
                        "covered_events": findings.get("covered_events", []),
                        "exclusions": findings.get("exclusions", []),
                    },
                ),
                self.message(
                    "Policy exclusions are ready for targeted exclusion review.",
                    to_agent="ExclusionCheckingAgent",
                    message_type="request",
                    metadata={"exclusions": findings.get("exclusions", [])},
                ),
            ],
        )

    @staticmethod
    def _verified_items(
        value: object,
        policy_text: str,
        *,
        required_polarity: str | None = None,
    ) -> list[dict[str, Any]]:
        """Model-only policy concepts are accepted only with evidence present in the source."""
        if not isinstance(value, list):
            return []
        verified = []
        for item in value:
            if not isinstance(item, dict):
                continue
            evidence = str(item.get("evidence_text", "")).strip()
            polarity_matches = required_polarity is None or clause_polarity(evidence) == required_polarity
            if evidence and evidence.casefold() in policy_text.casefold() and polarity_matches:
                verified.append(item)
        return verified

    @staticmethod
    def _merge_coverage_clauses(required: list[dict[str, Any]], additional: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged = []
        seen: set[tuple[str, str, str]] = set()
        for item in [*required, *additional]:
            identity = (
                str(item.get("concept", "")).casefold(),
                str(item.get("polarity", "unclear")).casefold(),
                str(item.get("evidence_text", "")).strip().casefold(),
            )
            if identity not in seen:
                seen.add(identity)
                merged.append(item)
        return merged

    @classmethod
    def _coverage_clauses(cls, policy_text: str) -> list[dict[str, Any]]:
        extracted = []
        for evidence_text in policy_clauses(policy_text):
            lower_clause = evidence_text.lower()
            polarity = clause_polarity(evidence_text)
            for concept, terms in cls.COVERAGE_PATTERNS.items():
                matched_terms = [term for term in terms if term in lower_clause]
                if matched_terms:
                    extracted.append(
                        {
                            "concept": concept,
                            "matched_terms": matched_terms,
                            "evidence_text": evidence_text,
                            "polarity": polarity,
                            "direct_match": any(term in lower_clause for term in terms[:2]),
                        }
                    )
        return extracted

    @classmethod
    def _exclusion_clauses(cls, policy_text: str) -> list[dict[str, Any]]:
        extracted = []
        clauses = policy_clauses(policy_text)
        for concept, terms in cls.EXCLUSION_PATTERNS.items():
            for evidence_text in clauses:
                lower_clause = evidence_text.lower()
                matched_terms = [term for term in terms if term in lower_clause]
                if matched_terms and clause_polarity(evidence_text) == "excluded":
                    extracted.append(
                        {
                            "concept": concept,
                            "matched_terms": matched_terms,
                            "evidence_text": evidence_text,
                            "polarity": "excluded",
                        }
                    )
                    break
        return extracted

    @classmethod
    def _structural_clauses(
        cls,
        document: PolicyDocument,
        policy_text: str,
    ) -> dict[ClauseType, list]:
        grouped: dict[ClauseType, list] = {
            ClauseType.CONDITION: [],
            ClauseType.LIMIT: [],
            ClauseType.DEFINITION: [],
        }
        for evidence_text in policy_clauses(policy_text):
            lower = evidence_text.casefold()
            concept, matched_terms = cls._clause_concept(lower)
            items: list[tuple[ClauseType, str]] = []
            if re.search(r"\b(?:means|is\s+defined\s+as|shall\s+mean)\b", lower):
                items.append((ClauseType.DEFINITION, "neutral"))
            if re.search(r"\b(?:limit(?:ed)?\s+to|maximum|up\s+to|not\s+exceed|sublimit)\b", lower):
                items.append((ClauseType.LIMIT, "neutral"))
            if (
                clause_polarity(evidence_text) == "conditional"
                or re.search(
                    r"\b(?:must|required|requires|only\s+if|provided\s+that|subject\s+to|unless|except)\b",
                    lower,
                )
            ):
                items.append((ClauseType.CONDITION, "conditional"))
            for clause_type, polarity in items:
                grouped[clause_type].append(
                    policy_clause(
                        document,
                        {
                            "concept": concept,
                            "matched_terms": matched_terms,
                            "evidence_text": evidence_text,
                            "polarity": polarity,
                            "direct_match": concept != "general",
                        },
                        clause_type=clause_type,
                    )
                )
        return grouped

    @classmethod
    def _clause_concept(cls, lower_clause: str) -> tuple[str, list[str]]:
        for concept, terms in cls.COVERAGE_PATTERNS.items():
            matched = [term for term in terms if term in lower_clause]
            if matched:
                return concept, matched
        return "general", []

    @staticmethod
    def _deduplicate_typed_clauses(clauses: list) -> list:
        deduplicated = []
        seen: set[str] = set()
        for clause in clauses:
            if clause.clause_id not in seen:
                seen.add(clause.clause_id)
                deduplicated.append(clause)
        return deduplicated

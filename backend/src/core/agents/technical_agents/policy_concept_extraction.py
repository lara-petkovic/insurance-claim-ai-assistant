from typing import Any

from core.agents.base import AgentContext, BaseAgent
from core.agents.technical_agents.policy_polarity import clause_polarity, policy_clauses
from core.agents.technical_agents.shared import _merge_dict_lists_by_key
from core.claim_validation import extract_policy_period, policy_domain_metadata
from core.models.agent import AgentResponse
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
        exclusions = [
            {"concept": concept, "matched_terms": [term for term in terms if term in lower]}
            for concept, terms in self.EXCLUSION_PATTERNS.items()
            if any(term in lower for term in terms)
        ]

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
        )
        findings: dict[str, Any] = {
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
        findings["covered_events"] = _merge_dict_lists_by_key(
            covered_events,
            verified_model_covered,
        )
        findings["exclusions"] = _merge_dict_lists_by_key(
            exclusions,
            verified_model_exclusions,
        )
        findings["coverage_clauses"] = self._merge_coverage_clauses(
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

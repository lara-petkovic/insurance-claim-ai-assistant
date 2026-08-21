from typing import Any

from core.agents.base import AgentContext, BaseAgent
from core.agents.technical_agents.policy_polarity import exact_text_in_source
from core.agents.technical_agents.shared import _functional_checklist, _merge_dict_lists_by_key
from core.models.agent import AgentResponse
from core.models.model_schemas import COVERAGE_SCHEMA
from models.model_client import get_model_client
from security.input_security import UNTRUSTED_INPUT_SYSTEM_RULE


class CoverageMatchingAgent(BaseAgent):
    """Compares claim facts with policy concepts and retrieved evidence to assess coverage."""

    name = "CoverageMatchingAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        claim_type = context.memory.get("ClaimExtractionAgent", {}).get("claim_type", "unknown")
        policy_concepts = context.memory.get("PolicyConceptExtractionAgent", {})
        coverage_clauses = policy_concepts.get("coverage_clauses", [])
        functional_checks = _functional_checklist(context)
        relevant_clauses = [item for item in coverage_clauses if item.get("concept") == claim_type]
        retrieved_evidence = []
        for response in reversed(context.responses):
            if response.agent_name == "RetrievalAgent":
                retrieved_evidence = [item.model_dump() for item in response.evidence if item.source == "policy"]
                break
        positive_clauses = [item for item in relevant_clauses if item.get("polarity") == "covered"]
        excluded_clauses = [
            item
            for item in relevant_clauses
            if item.get("polarity") == "excluded" and item.get("direct_match", True)
        ]
        conditional_clauses = [
            item
            for item in relevant_clauses
            if item.get("polarity") == "conditional" and item.get("direct_match", True)
        ]
        supporting_clauses = [
            item
            for item in positive_clauses
            if self._has_retrieved_support(item, retrieved_evidence)
        ]
        assessment = self._safe_rule_assessment(
            claim_type=claim_type,
            positive=positive_clauses,
            excluded=excluded_clauses,
            conditional=conditional_clauses,
            has_exact_support=bool(supporting_clauses),
        )
        fallback = {
            "coverage_assessment": assessment,
            "matched_policy_concepts": supporting_clauses if assessment == "covered" else relevant_clauses,
            "supporting_policy_passages": [item["evidence_text"] for item in supporting_clauses],
            "clause_polarities": sorted({str(item.get("polarity", "unclear")) for item in relevant_clauses}),
            "functional_checks_considered": functional_checks,
        }
        model_client = get_model_client()
        model_result = model_client.json_response(
            system=(
                "You are an insurance coverage matching agent. "
                "Return only valid JSON. Coverage rules, exclusions, limits, and conditions must come only from policy evidence. "
                + UNTRUSTED_INPUT_SYSTEM_RULE
            ),
            prompt=(
                "Compare the claim facts with the normalized policy concepts and decide coverage. "
                "Use this JSON shape: {coverage_assessment, matched_policy_concepts, explanation}. "
                "coverage_assessment must be covered, not_covered, possibly_covered, or unclear.\n\n"
                f"CLAIM FACTS:\n{context.memory.get('ClaimExtractionAgent', {})}\n\n"
                f"POLICY CONCEPTS:\n{context.memory.get('PolicyConceptExtractionAgent', {})}\n\n"
                f"FUNCTIONAL CHECKLIST:\n{functional_checks}\n\n"
                f"RETRIEVED POLICY EVIDENCE:\n{retrieved_evidence}"
            ),
            fallback=fallback,
            schema_name="coverage_assessment",
            json_schema=COVERAGE_SCHEMA,
        )
        source_policy_text = context.memory.get("DocumentIngestionAgent", {}).get(
            "policy_text", context.request.policy_text
        )
        model_matches = self._verified_model_matches(
            model_result.data.get("matched_policy_concepts"), source_policy_text, claim_type
        )
        final_findings: dict[str, Any] = {
            **fallback,
            **model_result.data,
            "model_used": model_result.used_model,
            "matched_policy_concepts": _merge_dict_lists_by_key(
                fallback["matched_policy_concepts"], model_matches
            ),
            "supporting_policy_passages": fallback["supporting_policy_passages"],
            "clause_polarities": fallback["clause_polarities"],
        }
        model_assessment = str(model_result.data.get("coverage_assessment", "unclear"))
        if excluded_clauses and not positive_clauses:
            final_findings["coverage_assessment"] = "not_covered"
        elif positive_clauses and excluded_clauses:
            final_findings["coverage_assessment"] = "unclear"
        elif model_result.used_model and model_assessment in {
            "covered", "not_covered", "possibly_covered", "unclear"
        }:
            final_findings["coverage_assessment"] = model_assessment
        else:
            final_findings["coverage_assessment"] = assessment
        if final_findings["coverage_assessment"] == "covered" and assessment != "covered":
            final_findings["coverage_assessment"] = "unclear"
        if final_findings["coverage_assessment"] != "covered":
            final_findings["supporting_policy_passages"] = []
        return self.respond(
            findings=final_findings,
            confidence=0.9 if final_findings.get("coverage_assessment") in {"covered", "not_covered"} else 0.4,
            warnings=(
                ["Used configured model for coverage matching."]
                if model_result.used_model
                else ["Coverage model unavailable; only exact, unambiguous policy wording was used."]
            ),
            requires_human_review=final_findings.get("coverage_assessment") != "covered",
            messages=[
                self.message(
                    f"Coverage assessment is {final_findings.get('coverage_assessment', 'unclear')} after checking policy concepts and retrieved evidence.",
                    to_agent="ExclusionCheckingAgent",
                    message_type="request",
                    metadata={
                        "claim_type": claim_type,
                        "matched_policy_concepts": final_findings.get("matched_policy_concepts", []),
                        "functional_checks": functional_checks,
                    },
                )
            ],
        )

    @staticmethod
    def _safe_rule_assessment(
        *,
        claim_type: str,
        positive: list[dict[str, Any]],
        excluded: list[dict[str, Any]],
        conditional: list[dict[str, Any]],
        has_exact_support: bool,
    ) -> str:
        if claim_type == "unknown" or (positive and excluded):
            return "unclear"
        if excluded:
            return "not_covered"
        if conditional:
            return "possibly_covered"
        if positive and has_exact_support:
            return "covered"
        return "unclear"

    @staticmethod
    def _has_retrieved_support(clause: dict[str, Any], evidence: list[dict[str, Any]]) -> bool:
        passage = str(clause.get("evidence_text", "")).strip()
        return bool(passage) and any(
            item.get("source") == "policy"
            and (exact_text_in_source(passage, str(item.get("text", "")))
                 or exact_text_in_source(item.get("text"), passage))
            for item in evidence
        )

    @staticmethod
    def _verified_model_matches(value: object, policy_text: str, claim_type: str) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [
            item
            for item in value
            if isinstance(item, dict)
            and item.get("concept") == claim_type
            and exact_text_in_source(item.get("evidence_text"), policy_text)
        ]

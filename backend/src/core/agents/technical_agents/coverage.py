from core.agents.technical_agents.shared import *

class CoverageMatchingAgent(BaseAgent):
    name = "CoverageMatchingAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        claim_type = context.memory.get("ClaimExtractionAgent", {}).get("claim_type", "unknown")
        covered_events = context.memory.get("PolicyConceptExtractionAgent", {}).get("covered_events", [])
        functional_checks = context.memory.get("HomeInsuranceFunctionalAgent", {}).get("checklist", [])
        matches = [event for event in covered_events if event.get("concept") == claim_type]
        assessment = "covered" if matches else "unclear"
        if claim_type == "storm_damage" and any(event.get("concept") == "storm_damage" for event in covered_events):
            assessment = "possibly_covered"
        if claim_type == "unknown":
            assessment = "unclear"
        fallback = {
            "coverage_assessment": assessment,
            "matched_policy_concepts": matches,
            "functional_checks_considered": functional_checks,
        }
        retrieved_evidence = []
        for response in context.responses:
            if response.agent_name == "RetrievalAgent":
                retrieved_evidence = [item.model_dump() for item in response.evidence]
                break
        model_client = get_model_client()
        model_result = model_client.json_response(
            system=(
                "You are an insurance coverage matching agent. "
                "Return only valid JSON. Use policy evidence conservatively."
            ),
            prompt=(
                "Compare the claim facts with the normalized policy concepts and decide coverage. "
                "Use this JSON shape: {coverage_assessment, matched_policy_concepts, explanation}. "
                "coverage_assessment must be covered, not_covered, possibly_covered, or unclear.\n\n"
                f"CLAIM FACTS:\n{context.memory.get('ClaimExtractionAgent', {})}\n\n"
                f"POLICY CONCEPTS:\n{context.memory.get('PolicyConceptExtractionAgent', {})}\n\n"
                f"FUNCTIONAL CHECKLIST:\n{functional_checks}\n\n"
                f"RETRIEVED EVIDENCE:\n{retrieved_evidence}"
            ),
            fallback=fallback,
        )
        final_findings = {**fallback, **model_result.data, "model_used": model_result.used_model}
        final_findings["matched_policy_concepts"] = _merge_dict_lists_by_key(
            matches,
            model_result.data.get("matched_policy_concepts"),
        )
        if assessment == "covered":
            final_findings["coverage_assessment"] = "covered"
        elif assessment == "unclear" and claim_type == "unknown":
            final_findings["coverage_assessment"] = "unclear"
        return AgentResponse(
            agent_name=self.name,
            findings=final_findings,
            confidence=0.82 if final_findings.get("matched_policy_concepts") else 0.4,
            warnings=(
                ["Used configured model for coverage matching."]
                if model_result.used_model
                else ([] if matches else ["No direct policy concept match found for the claim type."])
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


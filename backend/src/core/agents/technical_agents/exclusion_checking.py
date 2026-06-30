from core.agents.base import AgentContext, BaseAgent
from core.agents.technical_agents.shared import _contains, _functional_checklist, _merge_dict_lists_by_key
from core.models.agent import AgentResponse
from models.model_client import get_model_client


class ExclusionCheckingAgent(BaseAgent):
    """Checks whether policy exclusions or domain-specific exclusion risks apply."""

    name = "ExclusionCheckingAgent"
    agent_type = "validator"

    def run(self, context: AgentContext) -> AgentResponse:
        claim_text = context.request.claim_description.lower()
        policy_exclusions = context.memory.get("PolicyConceptExtractionAgent", {}).get("exclusions", [])
        targeted_checks = [
            item
            for item in _functional_checklist(context)
            if isinstance(item, dict) and item.get("target_agent") == self.name
        ]
        found = []
        for exclusion in policy_exclusions:
            concept = exclusion.get("concept")
            if concept == "unoccupied_home" and _contains(claim_text, "unoccupied", "empty", "away for months"):
                found.append({"concept": concept, "severity": "high", "reason": "Claim suggests home may have been unoccupied."})
            if concept == "gradual_damage" and _contains(claim_text, "months", "slow", "gradual", "long time"):
                found.append({"concept": concept, "severity": "high", "reason": "Claim suggests gradual damage."})
            if concept == "rot" and _contains(claim_text, "rot", "mold", "mould"):
                found.append({"concept": concept, "severity": "medium", "reason": "Claim mentions rot or mold."})
            if concept == "poor_maintenance" and _contains(claim_text, "maintenance", "old", "neglected"):
                found.append({"concept": concept, "severity": "medium", "reason": "Claim may involve maintenance condition."})
            if concept == "pipe_or_apparatus_itself" and _contains(claim_text, "replace the pipe", "repair the pipe"):
                found.append({"concept": concept, "severity": "medium", "reason": "Damage to the pipe itself may be excluded."})

        fallback = {"potential_exclusions": found, "targeted_checks": targeted_checks}
        model_client = get_model_client()
        model_result = model_client.json_response(
            system=(
                "You are an insurance exclusion checking agent. "
                "Return only valid JSON. Be conservative: uncertainty should be flagged for human review."
            ),
            prompt=(
                "Check whether policy exclusions may apply to this claim. "
                "Use this JSON shape: {potential_exclusions}. "
                "potential_exclusions must be an array of objects with concept, severity, reason, and evidence_text if available.\n\n"
                f"CLAIM DESCRIPTION:\n{context.request.claim_description}\n\n"
                f"CLAIM FACTS:\n{context.memory.get('ClaimExtractionAgent', {})}\n\n"
                f"POLICY EXCLUSIONS:\n{policy_exclusions}\n\n"
                f"FUNCTIONAL TARGETED CHECKS:\n{targeted_checks}\n\n"
                f"RETRIEVED POLICY EVIDENCE:\n"
                f"{[item.model_dump() for response in context.responses if response.agent_name == 'RetrievalAgent' for item in response.evidence]}"
            ),
            fallback=fallback,
        )
        final_findings = {**fallback, **model_result.data, "model_used": model_result.used_model,
                          "potential_exclusions": _merge_dict_lists_by_key(
                              found,
                              model_result.data.get("potential_exclusions"),
                          )}
        corroborated_concepts = {str(item.get("concept", "")).lower() for item in found}
        for exclusion in final_findings["potential_exclusions"]:
            concept = str(exclusion.get("concept", "")).lower()
            if concept not in corroborated_concepts and exclusion.get("severity") == "high":
                exclusion["severity"] = "medium"
                exclusion["requires_corroboration"] = True
        found = final_findings.get("potential_exclusions", found)

        return self.respond(
            findings=final_findings,
            confidence=0.72,
            warnings=(
                ["Used configured model for exclusion checking."]
                if model_result.used_model
                else ([] if not found else ["Potential exclusions require adjuster review."])
            ),
            requires_human_review=bool(found),
            messages=[
                self.message(
                    f"Exclusion review completed with {len(found)} potential exclusion(s).",
                    to_agent="CoverageMatchingAgent",
                    message_type="response",
                    metadata={"potential_exclusions": found, "targeted_checks": targeted_checks},
                )
            ],
        )

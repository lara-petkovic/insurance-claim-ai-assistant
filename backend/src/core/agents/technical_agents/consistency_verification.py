from core.agents.base import AgentContext, BaseAgent
from core.models.agent import AgentResponse


class ConsistencyVerificationAgent(BaseAgent):
    """Cross-checks claim facts, image findings, and required dates for inconsistencies."""

    name = "ConsistencyVerificationAgent"
    agent_type = "validator"

    def run(self, context: AgentContext) -> AgentResponse:
        claim_type = context.memory.get("ClaimExtractionAgent", {}).get("claim_type", "unknown")
        visual = context.memory.get("VisualEvidenceAgent", {})
        detected_damage = visual.get("detected_damage", "unknown")
        issues = []
        if detected_damage != "unknown" and claim_type != "unknown":
            visual_to_claim = {
                "theft_damage": "theft",
                "water_damage": "water_damage",
                "fire_damage": "fire_damage",
                "storm_damage": "storm_damage",
                "broken_glass": "broken_glass",
            }
            expected = visual_to_claim.get(detected_damage, detected_damage)
            if expected != claim_type:
                issues.append(f"Image suggests {detected_damage}, while claim was classified as {claim_type}.")
        if not context.request.incident_date:
            issues.append("Incident date is missing, so policy-period validation cannot be completed.")

        return self.respond(
            findings={"consistency_issues": issues},
            confidence=0.78 if not issues else 0.5,
            warnings=issues,
            requires_human_review=bool(issues),
            messages=[
                self.message(
                    f"Consistency verification completed with {len(issues)} issue(s).",
                    to_agent="OutputValidatorAgent",
                    message_type="validation",
                    metadata={"consistency_issues": issues},
                )
            ],
        )

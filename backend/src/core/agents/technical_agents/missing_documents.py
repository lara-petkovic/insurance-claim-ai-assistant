from core.agents.technical_agents.shared import *


class MissingDocumentsAgent(BaseAgent):
    """Checks whether required claim evidence or supporting documents are missing."""

    name = "MissingDocumentsAgent"
    agent_type = "validator"

    REQUIREMENTS = {
        "water_damage": ["damage photos", "plumber report", "repair estimate"],
        "storm_damage": ["damage photos", "weather report", "repair estimate"],
        "theft": ["police report", "proof of ownership"],
        "fire_damage": ["damage photos", "incident report", "repair estimate"],
        "broken_glass": ["damage photos", "repair estimate"],
        "vehicle_damage": ["damage photos", "repair estimate"],
        "medical": ["medical report", "medical receipts"],
        "baggage_loss": ["carrier or police report", "proof of ownership"],
        "trip_cancellation": ["booking confirmation", "cancellation evidence"],
    }

    def run(self, context: AgentContext) -> AgentResponse:
        claim_type = context.memory.get("ClaimExtractionAgent", {}).get("claim_type", "unknown")
        provided_names = " ".join(context.request.supporting_document_names).lower()
        targeted_checks = [
            item
            for item in _functional_checklist(context)
            if isinstance(item, dict) and item.get("target_agent") == self.name
        ]
        missing = []
        for requirement in self.REQUIREMENTS.get(claim_type, ["supporting evidence"]):
            if requirement == "damage photos":
                if not context.request.damage_image_filename:
                    missing.append(requirement)
                continue
            tokens = requirement.split()
            if not any(token in provided_names for token in tokens):
                missing.append(requirement)

        return self.respond(
            findings={"missing_documents": missing, "targeted_checks": targeted_checks},
            confidence=0.83,
            warnings=[] if not missing else ["Claim package is incomplete."],
            requires_human_review=bool(missing),
            messages=[
                self.message(
                    f"Evidence checklist completed with {len(missing)} missing document(s).",
                    to_agent="OutputValidatorAgent",
                    message_type="validation",
                    metadata={"missing_documents": missing, "targeted_checks": targeted_checks},
                )
            ],
        )

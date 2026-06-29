from __future__ import annotations

from core.agents.base import AgentContext, BaseAgent
from core.agents.constants import HOME_CHECKLIST_BY_CLAIM_TYPE, HOME_RULES_BY_CLAIM_TYPE
from core.models.agent import AgentResponse


class HomeInsuranceFunctionalAgent(BaseAgent):
    """Acts as a home-insurance domain expert and defines home-claim checks."""

    name = "HomeInsuranceFunctionalAgent"
    agent_type = "functional"

    def run(self, context: AgentContext) -> AgentResponse:
        claim_type = context.memory.get("ClaimExtractionAgent", {}).get("claim_type", "unknown")
        selected_rules = HOME_RULES_BY_CLAIM_TYPE.get(claim_type, [])
        selected_checklist = HOME_CHECKLIST_BY_CLAIM_TYPE.get(claim_type, [])
        instructions = [
            {
                "target_agent": item["target_agent"],
                "instruction": f"For {claim_type}, perform functional check: {item['check']}.",
                "priority": "high",
            }
            for item in selected_checklist
        ]
        return self.respond(
            findings={
                "rules_by_claim_type": HOME_RULES_BY_CLAIM_TYPE,
                "selected_claim_type": claim_type,
                "selected_rules": selected_rules,
                "checklist": selected_checklist,
                "instructions": instructions,
            },
            confidence=0.92,
            messages=[
                self.message(
                    f"Home insurance guidance prepared for {claim_type}: {len(selected_checklist)} targeted checks.",
                    to_agent="OrchestratorAgent",
                    message_type="guidance",
                    metadata={"claim_type": claim_type, "checks": selected_checklist, "instructions": instructions},
                )
            ],
        )

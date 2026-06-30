from core.agents.base import AgentContext, BaseAgent
from core.agents.technical_agents.shared import _functional_checklist
from core.models.agent import AgentResponse


class QueryRewriteAgent(BaseAgent):
    """Builds a retrieval query from claim facts and functional checklists."""

    name = "QueryRewriteAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        claim = context.memory.get("ClaimExtractionAgent", {})
        claim_type = str(claim.get("claim_type", "unknown"))
        functional_checks = _functional_checklist(context)
        check_terms = " ".join(str(item.get("check", "")) for item in functional_checks if isinstance(item, dict))
        rewritten_query = (
            f"{claim_type} {claim_type.replace('_', ' ')} {check_terms} "
            "covered exclusions conditions required evidence policy wording"
        ).strip()

        return self.respond(
            findings={
                "rewritten_query": rewritten_query,
                "source_claim_type": claim_type,
                "functional_checks_used": functional_checks,
            },
            confidence=0.82 if claim_type != "unknown" else 0.45,
            requires_human_review=claim_type == "unknown",
            messages=[
                self.message(
                    "Rewritten retrieval query prepared from claim type and functional checklist.",
                    to_agent="RetrievalAgent",
                    message_type="request",
                    metadata={"rewritten_query": rewritten_query},
                )
            ],
        )

from core.agents.technical_agents.shared import *


class CitationAgent(BaseAgent):
    """Attaches retrieved policy evidence as citations for the final decision."""

    name = "CitationAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        retrieval_evidence = []
        for response in context.responses:
            if response.agent_name == "RetrievalAgent":
                retrieval_evidence.extend(response.evidence)
        return self.respond(
            findings={"citation_count": len(retrieval_evidence)},
            evidence=retrieval_evidence[:4],
            confidence=0.84 if retrieval_evidence else 0.25,
            warnings=[] if retrieval_evidence else ["No citations available for final decision."],
            requires_human_review=not bool(retrieval_evidence),
            messages=[
                self.message(
                    f"Attached {len(retrieval_evidence[:4])} citation(s) from retrieved policy evidence.",
                    to_agent="OutputValidatorAgent",
                    message_type="handoff",
                    metadata={"citation_count": len(retrieval_evidence[:4])},
                )
            ],
        )

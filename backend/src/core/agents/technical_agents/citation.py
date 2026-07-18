from core.agents.base import AgentContext, BaseAgent
from core.models.agent import AgentResponse


class CitationAgent(BaseAgent):
    """Attaches policy rules and supporting-document facts with their original sources."""

    name = "CitationAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        retrieval_evidence = []
        for response in context.responses:
            if response.agent_name == "RetrievalAgent":
                retrieval_evidence.extend(response.evidence)
        policy_evidence = [item for item in retrieval_evidence if item.source == "policy"]
        supporting_evidence = [item for item in retrieval_evidence if item.source.startswith("supporting:")]
        citations = [*policy_evidence[:3], *supporting_evidence[:2]]
        return self.respond(
            findings={
                "citation_count": len(citations),
                "policy_citation_count": min(len(policy_evidence), 3),
                "supporting_document_citation_count": min(len(supporting_evidence), 2),
            },
            evidence=citations,
            confidence=0.84 if retrieval_evidence else 0.25,
            warnings=[] if retrieval_evidence else ["No citations available for final decision."],
            requires_human_review=not bool(retrieval_evidence),
            messages=[
                self.message(
                    f"Attached {len(citations)} citation(s) from policy and supporting-document evidence.",
                    to_agent="OutputValidatorAgent",
                    message_type="handoff",
                    metadata={"citation_count": len(citations)},
                )
            ],
        )

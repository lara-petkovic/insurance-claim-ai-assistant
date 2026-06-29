from __future__ import annotations

from core.agents.base import AgentContext, BaseAgent
from core.models.agent import AgentResponse


class FinalDecisionSynthesisAgent(BaseAgent):
    """Synthesizes all agent outputs into the final claim recommendation."""

    name = "FinalDecisionSynthesisAgent"
    agent_type = "synthesis"

    def run(self, context: AgentContext) -> AgentResponse:
        claim = context.memory.get("ClaimExtractionAgent", {})
        coverage = context.memory.get("CoverageMatchingAgent", {})
        validator_feedback = context.memory.get("OutputValidatorAgent", {}).get("feedback", [])
        exclusions = context.memory.get("ExclusionCheckingAgent", {}).get("potential_exclusions", [])
        missing_docs = context.memory.get("MissingDocumentsAgent", {}).get("missing_documents", [])
        consistency = context.memory.get("ConsistencyVerificationAgent", {}).get("consistency_issues", [])

        review_reasons = []
        if validator_feedback:
            review_reasons.append("validator feedback")
        if exclusions:
            review_reasons.append("potential exclusions")
        if missing_docs:
            review_reasons.append("missing documents")
        if consistency:
            review_reasons.append("consistency issues")

        return self.respond(
            findings={
                "claim_type": claim.get("claim_type", "unknown"),
                "coverage_assessment": coverage.get("coverage_assessment", "unclear"),
                "validator_feedback": validator_feedback,
                "review_reasons": review_reasons,
                "message_count": len(context.messages),
            },
            confidence=0.88 if not review_reasons else 0.68,
            requires_human_review=bool(review_reasons),
            messages=[
                self.message(
                    f"Final synthesis prepared after reviewing {len(context.messages)} inter-agent message(s).",
                    to_agent="OrchestratorAgent",
                    message_type="summary",
                    metadata={"review_reasons": review_reasons, "feedback_count": len(validator_feedback)},
                )
            ],
        )

from core.agents.technical_agents.shared import *


class RetrievalAgent(BaseAgent):
    """Retrieves policy evidence passages and retries with the rewritten query when useful."""

    name = "RetrievalAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        policy_text = context.memory.get("DocumentIngestionAgent", {}).get("policy_text", "")
        claim = context.memory.get("ClaimExtractionAgent", {})
        claim_type = claim.get("claim_type", "unknown")
        query = f"{claim_type} covered not covered exclusions required documents {context.request.claim_description}"
        attempts = []
        evidence = retrieve_passages(policy_text, query, top_k=5)
        attempts.append({"query": query, "retrieved_count": len(evidence)})
        rewritten_query = context.memory.get("QueryRewriteAgent", {}).get("rewritten_query")
        if len(evidence) < 2 and rewritten_query:
            retry_evidence = retrieve_passages(policy_text, rewritten_query, top_k=5)
            attempts.append({"query": rewritten_query, "retrieved_count": len(retry_evidence)})
            if len(retry_evidence) > len(evidence):
                query = rewritten_query
                evidence = retry_evidence
        return self.respond(
            findings={"query": query, "retrieved_count": len(evidence), "attempts": attempts},
            evidence=evidence,
            confidence=0.75 if evidence else 0.25,
            warnings=[] if evidence else ["Retrieval returned no matching policy clauses."],
            requires_human_review=not bool(evidence),
            messages=[
                self.message(
                    f"Retrieved {len(evidence)} policy clause(s) after {len(attempts)} retrieval attempt(s).",
                    to_agent="CoverageMatchingAgent",
                    message_type="response",
                    metadata={"attempts": attempts, "final_query": query},
                )
            ],
        )

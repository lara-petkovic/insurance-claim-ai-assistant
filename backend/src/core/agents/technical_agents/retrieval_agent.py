from core.agents.base import AgentContext, BaseAgent
from core.models.agent import AgentResponse
from data.retrieval import retrieve_passages


class RetrievalAgent(BaseAgent):
    """Retrieves policy evidence passages and retries with the rewritten query when useful."""

    name = "RetrievalAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        policy_text = context.memory.get("DocumentIngestionAgent", {}).get("policy_text", "")
        claim = context.memory.get("ClaimExtractionAgent", {})
        claim_type = claim.get("claim_type", "unknown")
        query = f"{claim_type} covered not covered exclusions required documents {context.request.claim_description}"
        attempts = []
        documents = context.request.supporting_documents
        policy_document = context.request.policy_document

        def search(search_query: str):
            policy = retrieve_passages(
                policy_text,
                search_query,
                source="policy",
                top_k=5,
                document=policy_document,
            )
            supporting = [
                item
                for document in documents
                if document.text.strip()
                for item in retrieve_passages(
                    document.text,
                    search_query,
                    source=f"supporting:{document.filename}",
                    top_k=3,
                    document=document,
                )
            ]
            supporting.sort(key=lambda item: item.score or 0, reverse=True)
            return policy, supporting[:5]

        policy_evidence, supporting_evidence = search(query)
        evidence = [*policy_evidence, *supporting_evidence]
        attempts.append({"query": query, "retrieved_count": len(evidence)})
        rewritten_query = context.memory.get("QueryRewriteAgent", {}).get("rewritten_query")
        if len(evidence) < 2 and rewritten_query:
            retry_policy, retry_supporting = search(rewritten_query)
            retry_evidence = [*retry_policy, *retry_supporting]
            attempts.append({"query": rewritten_query, "retrieved_count": len(retry_evidence)})
            if len(retry_evidence) > len(evidence):
                query = rewritten_query
                evidence = retry_evidence
                policy_evidence = retry_policy
                supporting_evidence = retry_supporting
        extraction_warnings = [
            f"{document.filename}: {warning}"
            for document in documents
            for warning in document.extraction_warnings
        ]
        return self.respond(
            findings={
                "query": query,
                "retrieved_count": len(evidence),
                "retrieved_policy_passages": [item.model_dump(mode="json") for item in policy_evidence],
                "retrieved_supporting_document_passages": [
                    item.model_dump(mode="json") for item in supporting_evidence
                ],
                "documents_searched": sum(bool(document.text.strip()) for document in documents),
                "extraction_warnings": extraction_warnings,
                "attempts": attempts,
            },
            evidence=evidence,
            confidence=0.75 if evidence else 0.25,
            warnings=[] if evidence else ["Retrieval returned no matching policy clauses."],
            requires_human_review=not bool(evidence),
            messages=[
                self.message(
                    f"Retrieved {len(policy_evidence)} policy and {len(supporting_evidence)} supporting passage(s) after {len(attempts)} retrieval attempt(s).",
                    to_agent="CoverageMatchingAgent",
                    message_type="response",
                    metadata={"attempts": attempts, "final_query": query},
                )
            ],
        )

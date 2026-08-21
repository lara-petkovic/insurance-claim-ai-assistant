from __future__ import annotations

from core.agents.base import AgentContext, BaseAgent
from core.models.agent import AgentResponse, EvidenceItem
from core.models.analysis import (
    AssessmentProposition,
    EvidenceReference,
    PolicyClause,
    PropositionStatus,
    PropositionType,
)
from core.provenance import evidence_reference
from security.input_security import detect_prompt_injection


class CitationAgent(BaseAgent):
    """Attaches exact retrieved passages to the propositions they ground."""

    name = "CitationAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        clauses = self._policy_clauses(context)
        retrieval_response = next(
            (
                response for response in reversed(context.responses)
                if response.agent_name == "RetrievalAgent"
            ),
            None,
        )
        retrieved = list(retrieval_response.evidence) if retrieval_response else []
        retrieved_by_clause_id = {
            item.policy_clause_id: item
            for item in retrieved
            if item.source == "policy" and item.policy_clause_id
        }
        self._replace_supporting_fact_propositions(context, retrieved)

        citations: dict[tuple[str, str], EvidenceItem] = {}
        proposition_citations: dict[str, list[str]] = {}
        uncited_propositions: list[str] = []
        for proposition in context.propositions:
            retained_evidence = [item for item in proposition.evidence if item.source_kind != "policy"]
            attached_references: list[EvidenceReference] = []
            referenced_clause_ids = [
                *proposition.supporting_policy_clause_ids,
                *proposition.contradicting_policy_clause_ids,
            ]
            for clause_id in dict.fromkeys(referenced_clause_ids):
                clause = clauses.get(clause_id)
                retrieved_item = retrieved_by_clause_id.get(clause_id)
                if clause is None or retrieved_item is None:
                    continue
                if not self._retrieval_matches_clause(retrieved_item, clause):
                    continue
                attached_references.append(
                    EvidenceReference(
                        **{
                            field: getattr(clause, field)
                            for field in EvidenceReference.model_fields
                            if field not in {"source_kind", "policy_clause_id"}
                        },
                        source_kind="policy",
                        policy_clause_id=clause.clause_id,
                    )
                )
            proposition.evidence = [*retained_evidence, *attached_references]
            proposition_citations[proposition.proposition_id] = [
                item.policy_clause_id
                for item in attached_references
                if item.policy_clause_id is not None
            ]
            if referenced_clause_ids and not attached_references:
                uncited_propositions.append(proposition.proposition_id)
            for reference in proposition.evidence:
                citation = self._evidence_item(reference, proposition.proposition_id)
                identity = (citation.source, citation.stable_location or citation.text)
                if identity in citations:
                    existing = citations[identity]
                    existing.proposition_ids = list(
                        dict.fromkeys([*existing.proposition_ids, proposition.proposition_id])
                    )
                else:
                    citations[identity] = citation

        evidence = list(citations.values())
        policy_count = sum(item.source == "policy" for item in evidence)
        supporting_count = len(evidence) - policy_count
        return self.respond(
            findings={
                "citation_count": len(evidence),
                "policy_citation_count": policy_count,
                "supporting_document_citation_count": supporting_count,
                "proposition_citations": proposition_citations,
                "uncited_proposition_ids": uncited_propositions,
            },
            evidence=evidence,
            confidence=0.9 if evidence and not uncited_propositions else 0.4,
            warnings=(
                [] if not uncited_propositions else
                ["One or more propositions could not be linked to an exact retrieved clause."]
            ),
            requires_human_review=bool(uncited_propositions),
            messages=[
                self.message(
                    f"Attached {len(evidence)} citation(s) to {len(context.propositions)} proposition(s).",
                    to_agent="OutputValidatorAgent",
                    message_type="handoff",
                    metadata={
                        "proposition_citations": proposition_citations,
                        "uncited_proposition_ids": uncited_propositions,
                    },
                )
            ],
        )

    @staticmethod
    def _policy_clauses(context: AgentContext) -> dict[str, PolicyClause]:
        findings = context.memory.get("PolicyConceptExtractionAgent", {})
        raw_clauses = findings.get("policy_clauses") or [
            *findings.get("coverage_clauses", []),
            *findings.get("exclusion_clauses", []),
            *findings.get("condition_clauses", []),
            *findings.get("limit_clauses", []),
            *findings.get("definition_clauses", []),
        ]
        clauses = {}
        for item in raw_clauses:
            try:
                clause = item if isinstance(item, PolicyClause) else PolicyClause.model_validate(item)
            except (TypeError, ValueError):
                continue
            clauses[clause.clause_id] = clause
        return clauses

    @staticmethod
    def _retrieval_matches_clause(item: EvidenceItem, clause: PolicyClause) -> bool:
        return (
            item.source == "policy"
            and item.policy_clause_id == clause.clause_id
            and item.text == clause.evidence_text
            and item.source_document_id == clause.source_document_id
            and item.source_filename == clause.source_filename
            and item.page == clause.page
            and item.section_heading == clause.section_heading
            and item.char_start == clause.char_start
            and item.char_end == clause.char_end
            and item.stable_location == clause.stable_location
        )

    @staticmethod
    def _evidence_item(reference: EvidenceReference, proposition_id: str) -> EvidenceItem:
        source = (
            "policy" if reference.source_kind == "policy" else
            "claim" if reference.source_kind == "claim" else
            f"supporting:{reference.source_filename}"
        )
        return EvidenceItem(
            source=source,
            text=reference.evidence_text,
            section=reference.section_heading,
            page=reference.page,
            score=reference.confidence,
            source_document_id=reference.source_document_id,
            source_filename=reference.source_filename,
            section_heading=reference.section_heading,
            char_start=reference.char_start,
            char_end=reference.char_end,
            stable_location=reference.stable_location,
            extraction_method=reference.extraction_method.value,
            verification_status=reference.verification_status.value,
            policy_clause_id=reference.policy_clause_id,
            proposition_ids=[proposition_id],
        )

    def _replace_supporting_fact_propositions(
        self,
        context: AgentContext,
        retrieved: list[EvidenceItem],
    ) -> None:
        context.propositions = [item for item in context.propositions if item.created_by != self.name]
        documents = {item.filename: item for item in context.request.supporting_documents}
        for index, item in enumerate(
            (item for item in retrieved if item.source.startswith("supporting:")), start=1
        ):
            filename = item.source_filename or item.source.removeprefix("supporting:")
            document = documents.get(filename)
            if document is None or detect_prompt_injection(document.text):
                continue
            reference = evidence_reference(document, item.text).model_copy(
                update={"source_kind": "supporting_document"}
            )
            context.propositions.append(
                AssessmentProposition(
                    proposition_id=f"supporting-fact-{index}",
                    proposition_type=PropositionType.CLAIM_FACT,
                    statement=f"Supporting document {filename} contains a relevant claim fact.",
                    status=PropositionStatus.SUPPORTED,
                    required_for_coverage=False,
                    evidence=[reference],
                    confidence=item.score or 0.5,
                    created_by=self.name,
                )
            )

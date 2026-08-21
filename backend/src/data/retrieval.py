from __future__ import annotations

import re
from collections import Counter

from core.models.agent import EvidenceItem
from core.models.analysis import ClauseType, PolicyClause, VerificationStatus, SourceDocument

# ¨y
def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def split_passages(text: str, max_chars: int = 900) -> list[str]:
    return [passage for passage, _, _ in split_passage_spans(text, max_chars=max_chars)]


def split_passage_spans(text: str, max_chars: int = 900) -> list[tuple[str, int, int]]:
    chunks: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n|(?<=\.)\s+(?=[A-Z])", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(current) + len(paragraph) > max_chars and current:
            chunks.append(current.strip())
            current = paragraph
        else:
            current = f"{current}\n{paragraph}".strip()
    if current:
        chunks.append(current.strip())
    spans: list[tuple[str, int, int]] = []
    cursor = 0
    for chunk in chunks:
        start = text.find(chunk, cursor)
        if start < 0:
            start = text.find(chunk)
        end = start + len(chunk) if start >= 0 else -1
        spans.append((chunk, start, end))
        if end >= 0:
            cursor = end
    return spans


def retrieve_passages(
    text: str,
    query: str,
    source: str = "policy",
    top_k: int = 5,
    *,
    document: SourceDocument | None = None,
) -> list[EvidenceItem]:
    query_terms = Counter(tokenize(query))
    if not query_terms:
        return []

    scored: list[tuple[float, str, int, int]] = []
    for passage, start, end in split_passage_spans(text):
        terms = Counter(tokenize(passage))
        score = sum(min(count, terms.get(term, 0)) for term, count in query_terms.items())
        if score:
            normalized = min(score / max(len(query_terms), 1), 1.0)
            scored.append((normalized, passage, start, end))

    scored.sort(key=lambda item: item[0], reverse=True)
    results = []
    for score, passage, start, _ in scored[:top_k]:
        excerpt = passage[:700]
        end = start + len(excerpt) if start >= 0 else None
        page = None
        if document is not None and start >= 0:
            for document_page in document.pages:
                if document_page.char_start <= start < document_page.char_end:
                    page = document_page.page_number
                    break
        results.append(
            EvidenceItem(
                source=source,
                text=excerpt,
                page=page,
                score=round(score, 3),
                source_document_id=document.document_id if document else None,
                source_filename=document.filename if document else None,
                char_start=start if start >= 0 else None,
                char_end=end,
                stable_location=(
                    f"page:{page}:chars:{start}-{end}" if page is not None else
                    f"chars:{start}-{end}" if start >= 0 else None
                ),
                extraction_method=document.extraction_method.value if document else None,
                verification_status=VerificationStatus.MACHINE_VERIFIED.value,
            )
        )
    return results


def retrieve_policy_clauses(
    clauses: list[PolicyClause],
    query: str,
    *,
    clause_type: ClauseType | str,
    claim_type: str,
    top_k: int = 10,
) -> list[EvidenceItem]:
    """Rank one policy-clause category without losing clause identity or provenance."""
    resolved_clause_type = ClauseType(clause_type)
    query_terms = Counter(tokenize(f"{claim_type} {query}"))
    ranked: list[tuple[float, PolicyClause]] = []
    for clause in clauses:
        if clause.clause_type is not resolved_clause_type:
            continue
        terms = Counter(tokenize(f"{clause.concept} {clause.evidence_text}"))
        overlap = sum(min(count, terms.get(term, 0)) for term, count in query_terms.items())
        concept_match = clause.concept in {claim_type, "general"}
        if not overlap and not concept_match:
            continue
        score = min((overlap + (3 if clause.concept == claim_type else 1 if concept_match else 0)) /
                    max(len(query_terms) + 3, 1), 1.0)
        ranked.append((score, clause))
    ranked.sort(key=lambda item: (item[0], item[1].direct_match), reverse=True)
    return [
        EvidenceItem(
            source="policy",
            text=clause.evidence_text,
            section=clause.section_heading,
            page=clause.page,
            score=round(score, 3),
            source_document_id=clause.source_document_id,
            source_filename=clause.source_filename,
            section_heading=clause.section_heading,
            char_start=clause.char_start,
            char_end=clause.char_end,
            stable_location=clause.stable_location,
            extraction_method=clause.extraction_method.value,
            verification_status=clause.verification_status.value,
            policy_clause_id=clause.clause_id,
            clause_type=clause.clause_type.value,
        )
        for score, clause in ranked[:top_k]
    ]

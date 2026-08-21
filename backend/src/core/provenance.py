"""Helpers for attaching exact source locations to extracted facts and clauses."""

from __future__ import annotations

from hashlib import sha256
import re
from typing import Any

from core.models.analysis import (
    ClaimFact,
    ClausePolarity,
    ClauseType,
    EvidenceReference,
    ExtractionMethod,
    PolicyClause,
    SourceDocument,
    VerificationStatus,
)


def evidence_reference(
    document: SourceDocument,
    evidence_text: str,
    *,
    extraction_method: ExtractionMethod | None = None,
    confidence: float = 1.0,
    verification_status: VerificationStatus = VerificationStatus.MACHINE_VERIFIED,
) -> EvidenceReference:
    exact_text = evidence_text.strip()
    start = document.text.find(exact_text) if exact_text else -1
    if start < 0 and exact_text:
        match = re.search(re.escape(exact_text), document.text, re.IGNORECASE)
        if match:
            start = match.start()
            exact_text = document.text[match.start() : match.end()]
    end = start + len(exact_text) if start >= 0 else None
    page = None
    if start >= 0:
        for document_page in document.pages:
            if document_page.char_start <= start < document_page.char_end:
                page = document_page.page_number
                break
    section = _excerpt_heading(exact_text) or (_section_heading(document.text, start) if start >= 0 else None)
    stable_location = (
        f"page:{page}:chars:{start}-{end}" if page is not None else
        f"chars:{start}-{end}" if start >= 0 else
        f"sha256:{sha256(exact_text.encode('utf-8')).hexdigest()[:20]}"
    )
    return EvidenceReference(
        source_document_id=document.document_id,
        source_filename=document.filename,
        page=page,
        section_heading=section,
        evidence_text=exact_text,
        char_start=start if start >= 0 else None,
        char_end=end,
        stable_location=stable_location,
        extraction_method=extraction_method or document.extraction_method,
        confidence=confidence,
        verification_status=verification_status if start >= 0 else VerificationStatus.UNVERIFIED,
    )


def policy_clause(
    document: SourceDocument,
    item: dict[str, Any],
    *,
    clause_type: ClauseType | None = None,
) -> PolicyClause:
    concept = str(item.get("concept", "other"))
    polarity = _polarity(item.get("polarity"))
    reference = evidence_reference(document, str(item.get("evidence_text", "")))
    resolved_type = clause_type or (
        ClauseType.EXCLUSION if polarity is ClausePolarity.EXCLUDED else ClauseType.COVERAGE
    )
    identity = f"{document.document_id}:{concept}:{reference.stable_location}:{polarity.value}"
    return PolicyClause(
        **reference.model_dump(),
        clause_id=f"clause_{sha256(identity.encode('utf-8')).hexdigest()[:20]}",
        concept=concept,
        clause_type=resolved_type,
        polarity=polarity,
        matched_terms=[str(term) for term in item.get("matched_terms", [])],
        direct_match=bool(item.get("direct_match", False)),
    )


def claim_fact(
    *,
    fact_type: str,
    value: object,
    claim_description: str,
    extraction_method: ExtractionMethod,
    confidence: float,
) -> ClaimFact:
    evidence_text = claim_description.strip() or "No claim description provided."
    end = len(evidence_text)
    identity = f"claim-description:{fact_type}:{value}:{evidence_text}"
    return ClaimFact(
        fact_id=f"fact_{sha256(identity.encode('utf-8')).hexdigest()[:20]}",
        fact_type=fact_type,
        value=value if isinstance(value, (str, int, float, bool)) or value is None else str(value),
        source_document_id="claim-description",
        source_filename="claim_description",
        section_heading="Claim description",
        evidence_text=evidence_text,
        char_start=0,
        char_end=end,
        stable_location=f"chars:0-{end}",
        extraction_method=extraction_method,
        confidence=confidence,
        verification_status=VerificationStatus.MACHINE_VERIFIED,
    )


def _polarity(value: object) -> ClausePolarity:
    try:
        return ClausePolarity(str(value))
    except ValueError:
        return ClausePolarity.UNCLEAR


def _section_heading(text: str, start: int) -> str | None:
    prefix = text[:start]
    for line in reversed(prefix.splitlines()):
        candidate = line.strip()
        if not candidate or len(candidate) > 140:
            continue
        if candidate.endswith(":") or candidate.isupper() or candidate[:1].isdigit():
            return candidate.rstrip(":")
    return None


def _excerpt_heading(evidence_text: str) -> str | None:
    first_line = evidence_text.splitlines()[0].strip() if evidence_text else ""
    if first_line and len(first_line) <= 140 and (first_line.isupper() or first_line.endswith(":")):
        return first_line.rstrip(":")
    return None


__all__ = ["claim_fact", "evidence_reference", "policy_clause"]

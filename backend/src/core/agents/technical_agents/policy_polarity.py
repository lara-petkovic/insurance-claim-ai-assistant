from __future__ import annotations

import re
from typing import Literal

ClausePolarity = Literal["covered", "excluded", "conditional", "unclear"]

_EXCLUDED = re.compile(
    r"\b(?:not\s+covered|is\s+excluded|are\s+excluded|no\s+cover(?:age)?|"
    r"does\s+not\s+cover|do\s+not\s+cover|we\s+will\s+not\s+cover|excludes?)\b",
    re.IGNORECASE,
)
_CONDITIONAL = re.compile(
    r"\b(?:may\s+be\s+covered|might\s+be\s+covered|covered\s+(?:only\s+)?if|"
    r"subject\s+to|provided\s+that|depending\s+on|unless|except(?:\s+when|\s+if|\s+for)?)\b",
    re.IGNORECASE,
)
_COVERED = re.compile(
    r"\b(?:is\s+covered|are\s+covered|what\s+is\s+covered|covered\s+events?|"
    r"covers?|cover\s+includes?|coverage\s+includes?)\b",
    re.IGNORECASE,
)
_HEADING = re.compile(
    r"\b(?:what\s+is\s+not\s+covered|what\s+is\s+covered|covered\s+events?|exclusions?)\s*:",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"[^.!?]+(?:[.!?]+|$)")


def clause_polarity(text: str) -> ClausePolarity:
    """Classify the effect of policy wording without treating topic mentions as cover."""
    if _CONDITIONAL.search(text):
        return "conditional"
    if _EXCLUDED.search(text):
        return "excluded"
    if _COVERED.search(text):
        return "covered"
    return "unclear"


def policy_clauses(policy_text: str) -> list[str]:
    """Split policy text while retaining list headings that establish clause polarity."""
    headings = list(_HEADING.finditer(policy_text))
    clauses: list[str] = []
    cursor = 0
    for index, heading in enumerate(headings):
        prefix = policy_text[cursor : heading.start()]
        clauses.extend(_sentences(prefix))
        limit = headings[index + 1].start() if index + 1 < len(headings) else len(policy_text)
        sentence_end = re.search(r"[.!?]", policy_text[heading.end() : limit])
        end = heading.end() + sentence_end.end() if sentence_end else limit
        clauses.append(policy_text[heading.start() : end].strip())
        cursor = end
    if not headings:
        clauses.extend(_sentences(policy_text))
    elif cursor < len(policy_text):
        clauses.extend(_sentences(policy_text[cursor:]))
    return [clause for clause in clauses if clause]


def exact_text_in_source(evidence_text: object, source_text: str) -> bool:
    evidence = str(evidence_text or "").strip()
    return bool(evidence) and evidence.casefold() in source_text.casefold()


def _sentences(text: str) -> list[str]:
    return [match.group(0).strip() for match in _SENTENCE.finditer(text) if match.group(0).strip()]

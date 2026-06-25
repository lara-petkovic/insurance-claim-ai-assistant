from __future__ import annotations

import re
from collections import Counter

from core.schemas.agent import EvidenceItem


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def split_passages(text: str, max_chars: int = 900) -> list[str]:
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
    return chunks


def retrieve_passages(policy_text: str, query: str, top_k: int = 5) -> list[EvidenceItem]:
    query_terms = Counter(tokenize(query))
    if not query_terms:
        return []

    scored: list[tuple[float, str]] = []
    for passage in split_passages(policy_text):
        terms = Counter(tokenize(passage))
        score = sum(min(count, terms.get(term, 0)) for term, count in query_terms.items())
        if score:
            normalized = score / max(len(query_terms), 1)
            scored.append((normalized, passage))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        EvidenceItem(source="policy", text=passage[:700], score=round(score, 3))
        for score, passage in scored[:top_k]
    ]

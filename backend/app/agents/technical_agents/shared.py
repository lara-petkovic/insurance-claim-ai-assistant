from __future__ import annotations

import re
from pathlib import Path

from app.agents.base import AgentContext, BaseAgent
from app.schemas.agent import AgentResponse, EvidenceItem
from app.schemas.claim import ImageAssessment, ImageAuthenticity
from app.services.model_client import get_model_client
from app.services.retrieval import retrieve_passages


def _contains(text: str, *terms: str) -> bool:
    normalized = text.lower()
    return any(term in normalized for term in terms)


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_dict_list(value: object, *, default_key: str = "text") -> list[dict]:
    normalized = []
    for item in _as_list(value):
        if isinstance(item, dict):
            normalized.append(item)
        else:
            normalized.append({default_key: str(item)})
    return normalized


__all__ = [
    "re",
    "Path",
    "AgentContext",
    "BaseAgent",
    "AgentResponse",
    "EvidenceItem",
    "ImageAssessment",
    "ImageAuthenticity",
    "get_model_client",
    "retrieve_passages",
    "_contains",
    "_as_list",
    "_as_dict_list",
]

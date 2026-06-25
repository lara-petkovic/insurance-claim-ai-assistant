from __future__ import annotations

import re
from pathlib import Path

from core.agents.base import AgentContext, BaseAgent
from core.schemas.agent import AgentResponse, EvidenceItem
from core.schemas.claim import ImageAssessment, ImageAuthenticity
from data.retrieval import retrieve_passages
from models.model_client import get_model_client


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


def _merge_dict_lists_by_key(
    required: object,
    additional: object,
    *,
    key: str = "concept",
) -> list[dict]:
    """Merge model output into deterministic findings without dropping known facts."""
    merged: list[dict] = []
    positions: dict[str, int] = {}

    for item in [*_as_dict_list(required, default_key=key), *_as_dict_list(additional, default_key=key)]:
        identity = str(item.get(key, "")).strip().lower()
        if identity and identity in positions:
            index = positions[identity]
            merged[index] = {**merged[index], **item}
            continue
        if identity:
            positions[identity] = len(merged)
        merged.append(item)

    return merged


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
    "_merge_dict_lists_by_key",
]

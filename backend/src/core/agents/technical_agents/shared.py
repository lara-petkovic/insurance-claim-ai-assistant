from __future__ import annotations

from core.agents.base import AgentContext


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


def specialized_functional_agent_name(insurance_type: str) -> str:
    return {
        "auto": "AutoInsuranceFunctionalAgent",
        "travel": "TravelInsuranceFunctionalAgent",
    }.get(insurance_type.lower(), "HomeInsuranceFunctionalAgent")


def _functional_checklist(context: AgentContext) -> list:
    agent_name = specialized_functional_agent_name(context.request.insurance_type)
    return context.memory.get(agent_name, {}).get("checklist", [])


__all__ = [
    "_contains",
    "_as_list",
    "_as_dict_list",
    "_merge_dict_lists_by_key",
    "specialized_functional_agent_name",
    "_functional_checklist",
]

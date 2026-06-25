from __future__ import annotations

from datetime import datetime
from typing import Any


def log_agent_event(agent_name: str, message: str, **details: Any) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    detail_text = ""
    if details:
        safe_details = {key: _summarize(value) for key, value in details.items()}
        detail_text = " | " + " ".join(f"{key}={value}" for key, value in safe_details.items())
    print(f"[{timestamp}] [{agent_name}] {message}{detail_text}", flush=True)


def _summarize(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)) or value is None:
        return str(value)
    if isinstance(value, str):
        cleaned = " ".join(value.split())
        return repr(cleaned[:117] + "...") if len(cleaned) > 120 else repr(cleaned)
    if isinstance(value, list):
        return f"list({len(value)})"
    if isinstance(value, dict):
        return f"dict({len(value)})"
    return type(value).__name__

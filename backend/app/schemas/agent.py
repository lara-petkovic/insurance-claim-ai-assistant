from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


AgentStatus = Literal["completed", "warning", "failed", "skipped"]


class EvidenceItem(BaseModel):
    source: str
    text: str
    section: str | None = None
    page: int | None = None
    score: float | None = None


class AgentResponse(BaseModel):
    agent_name: str
    status: AgentStatus = "completed"
    findings: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    requires_human_review: bool = False


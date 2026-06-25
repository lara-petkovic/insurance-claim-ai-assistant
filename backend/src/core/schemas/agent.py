from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AgentStatus = Literal["completed", "warning", "failed", "skipped"]
AgentType = Literal["orchestrator", "technical", "functional", "validator", "synthesis"]
MessageType = Literal["handoff", "request", "response", "guidance", "feedback", "validation", "summary"]


class EvidenceItem(BaseModel):
    source: str
    text: str
    section: str | None = None
    page: int | None = None
    score: float | None = None


class AgentMessage(BaseModel):
    from_agent: str
    to_agent: str | None = None
    message_type: MessageType = "summary"
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    agent_name: str
    agent_type: AgentType = "technical"
    status: AgentStatus = "completed"
    findings: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    messages: list[AgentMessage] = Field(default_factory=list)

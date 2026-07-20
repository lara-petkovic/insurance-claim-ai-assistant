from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

class AgentStatus(StrEnum):
    COMPLETED = "completed"
    WARNING = "warning"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentType(StrEnum):
    ORCHESTRATOR = "orchestrator"
    TECHNICAL = "technical"
    FUNCTIONAL = "functional"
    VALIDATOR = "validator"
    SYNTHESIS = "synthesis"


class MessageType(StrEnum):
    HANDOFF = "handoff"
    REQUEST = "request"
    RESPONSE = "response"
    GUIDANCE = "guidance"
    FEEDBACK = "feedback"
    VALIDATION = "validation"
    SUMMARY = "summary"


class EvidenceItem(BaseModel):
    source: str
    text: str
    section: str | None = None
    page: int | None = None
    score: float | None = None


class AgentMessage(BaseModel):
    from_agent: str
    to_agent: str | None = None
    message_type: MessageType = MessageType.SUMMARY
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    agent_name: str
    agent_type: AgentType = AgentType.TECHNICAL
    status: AgentStatus = AgentStatus.COMPLETED
    findings: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    messages: list[AgentMessage] = Field(default_factory=list)

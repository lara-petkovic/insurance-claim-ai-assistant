from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, SerializeAsAny

from core.models.analysis import AgentFindings, GenericAgentFindings

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
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    source_document_id: str | None = None
    source_filename: str | None = None
    section_heading: str | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    stable_location: str | None = None
    extraction_method: str | None = None
    verification_status: str | None = None
    policy_clause_id: str | None = None
    clause_type: str | None = None
    proposition_ids: list[str] = Field(default_factory=list)


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
    findings: SerializeAsAny[AgentFindings] = Field(default_factory=GenericAgentFindings)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    messages: list[AgentMessage] = Field(default_factory=list)

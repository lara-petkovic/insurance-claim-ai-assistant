from __future__ import annotations

from typing import Any

from core.models.agent import AgentMessage, AgentResponse, AgentStatus, AgentType, MessageType
from core.models.analysis import AgentFindings
from core.models.run_state import ClaimAnalysisRunState


AgentContext = ClaimAnalysisRunState


class BaseAgent:
    """Base interface for agents that perform one focused unit of work."""

    name = "BaseAgent"
    agent_type: AgentType = AgentType.TECHNICAL

    def run(self, context: AgentContext) -> AgentResponse:
        raise NotImplementedError

    def message(
        self,
        content: str,
        *,
        to_agent: str | None = None,
        message_type: MessageType = MessageType.SUMMARY,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMessage:
        return AgentMessage(
            from_agent=self.name,
            to_agent=to_agent,
            message_type=message_type,
            content=content,
            metadata=metadata or {},
        )

    def respond(
        self,
        *,
        findings: AgentFindings | dict[str, Any] | None = None,
        evidence: list | None = None,
        confidence: float = 0.0,
        warnings: list[str] | None = None,
        requires_human_review: bool = False,
        messages: list[AgentMessage] | None = None,
        status: AgentStatus = AgentStatus.COMPLETED,
    ) -> AgentResponse:
        return AgentResponse(
            agent_name=self.name,
            agent_type=self.agent_type,
            status=status,
            findings=findings or {},
            evidence=evidence or [],
            confidence=confidence,
            warnings=warnings or [],
            requires_human_review=requires_human_review,
            messages=messages or [],
        )

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.models.agent import AgentMessage, AgentResponse, AgentStatus, AgentType, MessageType
from core.models.claim import ClaimRequestData


@dataclass
class AgentContext:
    """Carries the request, shared memory, responses, and messages through an agent run."""

    request: ClaimRequestData
    responses: list[AgentResponse] = field(default_factory=list)
    memory: dict[str, Any] = field(default_factory=dict)
    messages: list[AgentMessage] = field(default_factory=list)

    def add(self, response: AgentResponse) -> AgentResponse:
        self.responses.append(response)
        self.memory[response.agent_name] = response.findings
        self.messages.extend(response.messages)
        return response

    def replace(self, response: AgentResponse) -> AgentResponse:
        self.responses.append(response)
        self.memory[response.agent_name] = response.findings
        self.messages.extend(response.messages)
        return response


class BaseAgent:
    """Base interface for agents that perform one focused unit of work."""

    name = "BaseAgent"
    agent_type: AgentType = "technical"

    def run(self, context: AgentContext) -> AgentResponse:
        raise NotImplementedError

    def message(
        self,
        content: str,
        *,
        to_agent: str | None = None,
        message_type: MessageType = "summary",
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
        findings: dict[str, Any] | None = None,
        evidence: list | None = None,
        confidence: float = 0.0,
        warnings: list[str] | None = None,
        requires_human_review: bool = False,
        messages: list[AgentMessage] | None = None,
        status: AgentStatus = "completed",
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

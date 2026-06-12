from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.schemas.agent import AgentResponse
from app.schemas.claim import ClaimRequestData


@dataclass
class AgentContext:
    request: ClaimRequestData
    responses: list[AgentResponse] = field(default_factory=list)
    memory: dict[str, Any] = field(default_factory=dict)

    def add(self, response: AgentResponse) -> AgentResponse:
        self.responses.append(response)
        self.memory[response.agent_name] = response.findings
        return response


class BaseAgent:
    name = "BaseAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        raise NotImplementedError


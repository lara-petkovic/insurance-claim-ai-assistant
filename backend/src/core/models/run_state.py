"""Validated state carried through one claim-analysis run."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny, field_validator

from core.models.agent import AgentMessage, AgentResponse
from core.models.analysis import (
    AgentFindings,
    AssessmentProposition,
    GenericAgentFindings,
    InvestigationTask,
    TaskStatus,
)
from core.models.claim import ClaimRequestData


class ClaimAnalysisRunState(BaseModel):
    """Typed shared memory, work plan, evidence propositions, and agent trace."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    request: ClaimRequestData
    responses: list[AgentResponse] = Field(default_factory=list)
    memory: dict[str, SerializeAsAny[AgentFindings]] = Field(default_factory=dict)
    messages: list[AgentMessage] = Field(default_factory=list)
    tasks: list[InvestigationTask] = Field(default_factory=list)
    propositions: list[AssessmentProposition] = Field(default_factory=list)

    @field_validator("memory", mode="before")
    @classmethod
    def coerce_memory(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        return {
            str(key): item if isinstance(item, AgentFindings) else GenericAgentFindings.model_validate(item)
            for key, item in value.items()
        }

    def add(self, response: AgentResponse) -> AgentResponse:
        self.responses.append(response)
        self.memory[response.agent_name] = response.findings
        self.messages.extend(response.messages)
        self._mark_task(response)
        return response

    def replace(self, response: AgentResponse) -> AgentResponse:
        return self.add(response)

    def set_plan(self, agent_names: list[str]) -> None:
        self.tasks = [
            InvestigationTask(
                task_id=f"task-{index}-{agent_name}",
                agent_name=agent_name,
                objective=f"Run {agent_name} for this claim analysis.",
            )
            for index, agent_name in enumerate(agent_names, start=1)
        ]

    def _mark_task(self, response: AgentResponse) -> None:
        for task in self.tasks:
            if task.agent_name == response.agent_name and task.status is TaskStatus.PENDING:
                task.status = (
                    TaskStatus.FAILED if response.status == "failed" else TaskStatus.COMPLETED
                )
                break


__all__ = ["ClaimAnalysisRunState"]

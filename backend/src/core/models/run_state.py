"""Validated state carried through one claim-analysis run."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, SerializeAsAny, field_validator

from time import monotonic

from core.models.agent import AgentMessage, AgentResponse
from core.models.analysis import (
    AgentFindings,
    AssessmentProposition,
    GenericAgentFindings,
    InvestigationTask,
    OrchestrationAction,
    OrchestrationLimits,
    OrchestrationPhase,
    OrchestrationStopReason,
    OrchestrationUsage,
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
    phase: OrchestrationPhase = OrchestrationPhase.PLANNING
    limits: OrchestrationLimits = Field(default_factory=OrchestrationLimits)
    usage: OrchestrationUsage = Field(default_factory=OrchestrationUsage)
    actions: list[OrchestrationAction] = Field(default_factory=list)
    stop_reason: OrchestrationStopReason | None = None
    stop_detail: str | None = None
    _started_at: float = PrivateAttr(default_factory=monotonic)

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

    def add_tasks(self, tasks: list[InvestigationTask]) -> None:
        existing = {task.task_id for task in self.tasks}
        self.tasks.extend(task for task in tasks if task.task_id not in existing)

    def start_task(self, task: InvestigationTask) -> None:
        task.status = TaskStatus.IN_PROGRESS

    def finish_task(
        self,
        task: InvestigationTask,
        *,
        status: TaskStatus,
        summary: str,
        executor: str,
    ) -> None:
        task.status = status
        task.result_summary = summary
        self.actions.append(
            OrchestrationAction(
                task_id=task.task_id,
                task_type=task.task_type,
                selected_by="InvestigationPlannerAgent",
                executor=executor,
                reason=task.selection_reason,
                outcome=status,
                detail=summary,
                repair_iteration=self.usage.repair_iterations,
            )
        )

    def refresh_elapsed(self) -> float:
        self.usage.elapsed_seconds = max(0.0, monotonic() - self._started_at)
        return self.usage.elapsed_seconds

    def budget_allows(self, task: InvestigationTask) -> tuple[bool, str | None]:
        if self.refresh_elapsed() >= self.limits.max_seconds:
            return False, "maximum orchestration time reached"
        if self.usage.model_calls + task.expected_model_calls > self.limits.max_model_calls:
            return False, "maximum model calls reached"
        if (
            self.usage.estimated_cost_usd + task.estimated_cost_usd
            > self.limits.max_estimated_cost_usd
        ):
            return False, "maximum estimated cost reached"
        return True, None

    def reserve_budget(self, task: InvestigationTask) -> None:
        self.usage.model_calls += task.expected_model_calls
        self.usage.estimated_cost_usd = round(
            self.usage.estimated_cost_usd + task.estimated_cost_usd,
            6,
        )

    def stop(self, reason: OrchestrationStopReason, detail: str) -> None:
        self.stop_reason = reason
        self.stop_detail = detail
        self.phase = OrchestrationPhase.STOPPED
        self.refresh_elapsed()

    def _mark_task(self, response: AgentResponse) -> None:
        for task in self.tasks:
            if task.agent_name == response.agent_name and task.status in {
                TaskStatus.PENDING,
                TaskStatus.IN_PROGRESS,
            }:
                task.status = (
                    TaskStatus.FAILED if response.status == "failed" else TaskStatus.COMPLETED
                )
                break


__all__ = ["ClaimAnalysisRunState"]

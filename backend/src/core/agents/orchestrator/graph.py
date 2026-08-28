"""Small explicit execution graph for bounded claim investigation."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from core.agents.base import AgentContext
from core.agents.orchestrator.planning import InvestigationPlannerAgent
from core.agents.orchestrator.roles import CoverageAnalystAgent, EvidenceCriticAgent
from core.agents.orchestrator.services import ControlledServiceRegistry
from core.models.agent import AgentResponse
from core.models.analysis import (
    InvestigationTask,
    InvestigationTaskType,
    OrchestrationPhase,
    OrchestrationStopReason,
    TaskStatus,
)


class BoundedInvestigationGraph:
    """Executes typed nodes, with only targeted bounded cycles back from critique."""

    def __init__(
        self,
        *,
        planner: InvestigationPlannerAgent | None = None,
        analyst: CoverageAnalystAgent | None = None,
        critic: EvidenceCriticAgent | None = None,
        services: ControlledServiceRegistry | None = None,
    ) -> None:
        self.planner = planner or InvestigationPlannerAgent()
        self.analyst = analyst or CoverageAnalystAgent()
        self.critic = critic or EvidenceCriticAgent()
        self.services = services or ControlledServiceRegistry()

    def execute(self, context: AgentContext) -> Iterator[dict[str, Any]]:
        plan_task = InvestigationTask(
            task_id="task-00-plan",
            task_type=InvestigationTaskType.PLAN,
            agent_name=self.planner.name,
            assigned_role=self.planner.name,
            objective="Plan typed work for unresolved claim evidence.",
            selection_reason="Every run starts by converting unresolved state into bounded typed tasks.",
            expected_model_calls=1,
            estimated_cost_usd=0.003,
        )
        context.add_tasks([plan_task])
        active_task: InvestigationTask | None = None
        try:
            allowed, reason = context.budget_allows(plan_task)
            if not allowed:
                context.finish_task(
                    plan_task,
                    status=TaskStatus.SKIPPED,
                    summary=reason or "Planning budget unavailable.",
                    executor=self.planner.name,
                )
                context.stop(OrchestrationStopReason.BUDGET_EXHAUSTED, reason or "Planning budget unavailable.")
                yield {"kind": "stopped"}
                yield from self._synthesize(context)
                return
            context.reserve_budget(plan_task)
            context.start_task(plan_task)
            active_task = plan_task
            yield {"kind": "task_started", "task": plan_task}
            plan_response = context.add(self.planner.run(context))
            # Preserve the Phase 1-4 trace key while the real reasoning role is explicit.
            legacy_plan_response = plan_response.model_copy(
                update={"agent_name": "DynamicPlanningAgent", "messages": []}
            )
            context.add(legacy_plan_response)
            planned_tasks = [
                InvestigationTask.model_validate(item)
                for item in plan_response.findings.get("tasks", [])
            ]
            requested_task_ids = {
                str(task_id)
                for message in plan_response.messages
                for task_id in message.metadata.get("task_ids", [])
            }
            planned_tasks = [
                task for task in planned_tasks if task.task_id in requested_task_ids
            ]
            context.add_tasks(planned_tasks)
            context.finish_task(
                plan_task,
                status=TaskStatus.COMPLETED,
                summary=f"Selected {len(planned_tasks)} typed task(s).",
                executor=self.planner.name,
            )
            active_task = None
            yield {
                "kind": "plan_completed",
                "task": plan_task,
                "responses": [plan_response],
                "planned_agents": plan_response.findings.get("planned_agents", []),
                "tasks": planned_tasks,
            }

            context.phase = OrchestrationPhase.INVESTIGATION
            queue = list(planned_tasks)
            index = 0
            while index < len(queue) and context.stop_reason is None:
                task = queue[index]
                index += 1
                dependency_failure = self._dependency_failure(context, task)
                if dependency_failure:
                    context.finish_task(
                        task,
                        status=TaskStatus.SKIPPED,
                        summary=dependency_failure,
                        executor=task.tool_name or task.assigned_role,
                    )
                    yield {"kind": "task_completed", "task": task, "responses": []}
                    continue
                allowed, reason = context.budget_allows(task)
                if not allowed:
                    context.finish_task(
                        task,
                        status=TaskStatus.SKIPPED,
                        summary=reason or "Task budget unavailable.",
                        executor=task.tool_name or task.assigned_role,
                    )
                    context.stop(
                        OrchestrationStopReason.BUDGET_EXHAUSTED,
                        reason or "A bounded task could not be scheduled.",
                    )
                    break
                context.reserve_budget(task)
                context.start_task(task)
                active_task = task
                context.phase = (
                    OrchestrationPhase.CRITIQUE
                    if task.task_type is InvestigationTaskType.CRITIQUE_EVIDENCE
                    else OrchestrationPhase.REPAIR
                    if task.attempt
                    else OrchestrationPhase.INVESTIGATION
                )
                yield {"kind": "task_started", "task": task}
                responses, repair_tasks = self._execute_task(context, task)
                summary = self._task_summary(responses)
                context.finish_task(
                    task,
                    status=TaskStatus.COMPLETED,
                    summary=summary,
                    executor=task.tool_name or task.assigned_role,
                )
                active_task = None
                yield {"kind": "task_completed", "task": task, "responses": responses}

                if context.refresh_elapsed() >= context.limits.max_seconds:
                    context.stop(
                        OrchestrationStopReason.BUDGET_EXHAUSTED,
                        "Maximum orchestration time reached after the current bounded task completed.",
                    )
                    break

                if task.task_type is InvestigationTaskType.CRITIQUE_EVIDENCE:
                    critic_response = responses[-1]
                    verdict = str(critic_response.findings.get("verdict", "uncertain"))
                    if repair_tasks:
                        if context.usage.repair_iterations >= context.limits.max_repair_iterations:
                            context.stop(
                                OrchestrationStopReason.BUDGET_EXHAUSTED,
                                "Maximum repair iterations reached with rejected propositions unresolved.",
                            )
                        else:
                            context.usage.repair_iterations += 1
                            context.add_tasks(repair_tasks)
                            queue.extend(repair_tasks)
                    elif verdict == "accepted":
                        context.stop(
                            OrchestrationStopReason.SUFFICIENT_EVIDENCE,
                            "The critic accepted all required grounded propositions.",
                        )
                    else:
                        context.stop(
                            OrchestrationStopReason.UNAVOIDABLE_UNCERTAINTY,
                            "Available evidence cannot resolve the remaining uncertainty through targeted repair.",
                        )

            if context.stop_reason is None:
                context.stop(
                    OrchestrationStopReason.UNAVOIDABLE_UNCERTAINTY,
                    "The bounded graph completed without a critic acceptance decision.",
                )
            yield {"kind": "stopped"}
        except Exception as exc:
            if active_task is not None and active_task.status is TaskStatus.IN_PROGRESS:
                context.finish_task(
                    active_task,
                    status=TaskStatus.FAILED,
                    summary=f"Task failed: {type(exc).__name__}.",
                    executor=active_task.tool_name or active_task.assigned_role,
                )
            context.stop(
                OrchestrationStopReason.FAILURE,
                f"Execution failed in a controlled graph node: {type(exc).__name__}.",
            )
            yield {"kind": "failed", "error": exc}
        yield from self._synthesize(context)

    def _execute_task(
        self,
        context: AgentContext,
        task: InvestigationTask,
    ) -> tuple[list[AgentResponse], list[InvestigationTask]]:
        if task.task_type is InvestigationTaskType.ANALYZE_COVERAGE:
            responses = self.analyst.run_task(context, task)
            # Component responses were added by the role so their findings are immediately consumable.
            context.add(responses[-1])
            return responses, []
        if task.task_type is InvestigationTaskType.CRITIQUE_EVIDENCE:
            responses, repair_tasks = self.critic.run_task(context, task)
            # The critic added the deterministic validator output before making its decision.
            context.add(responses[-1])
            requested_ids = {
                str(task_id)
                for message in responses[-1].messages
                if message.message_type == "request"
                for task_id in message.metadata.get("repair_task_ids", [])
            }
            # Inter-role requests are executable: only tasks explicitly requested by the
            # critic's typed message are admitted back into the graph.
            admitted_repairs = [
                repair for repair in repair_tasks if repair.task_id in requested_ids
            ]
            return responses, admitted_repairs
        responses = self.services.execute(context, task)
        for response in responses:
            context.add(response)
        return responses, []

    def _synthesize(self, context: AgentContext) -> Iterator[dict[str, Any]]:
        context.phase = OrchestrationPhase.SYNTHESIS
        task = InvestigationTask(
            task_id="task-final-synthesize",
            task_type=InvestigationTaskType.SYNTHESIZE,
            agent_name="FinalDecisionSynthesisAgent",
            assigned_role="InvestigationPlannerAgent",
            tool_name="FinalDecisionSynthesisAgent",
            objective="Summarize the bounded investigation without resolving unsupported uncertainty.",
            selection_reason=f"The graph stopped with {context.stop_reason or 'no stop reason'} and requires API output.",
        )
        context.add_tasks([task])
        context.start_task(task)
        yield {"kind": "task_started", "task": task}
        try:
            responses = self.services.execute(context, task)
            for response in responses:
                context.add(response)
            context.finish_task(
                task,
                status=TaskStatus.COMPLETED,
                summary=self._task_summary(responses),
                executor=task.tool_name or task.assigned_role,
            )
            yield {"kind": "task_completed", "task": task, "responses": responses}
        except Exception as exc:
            context.stop(OrchestrationStopReason.FAILURE, "Final synthesis service failed.")
            context.finish_task(
                task,
                status=TaskStatus.FAILED,
                summary=f"Synthesis failed: {type(exc).__name__}.",
                executor=task.tool_name or task.assigned_role,
            )
            yield {"kind": "failed", "error": exc}
        context.phase = OrchestrationPhase.STOPPED

    @staticmethod
    def _dependency_failure(context: AgentContext, task: InvestigationTask) -> str | None:
        by_id = {item.task_id: item for item in context.tasks}
        incomplete = [
            dependency
            for dependency in task.depends_on
            if dependency not in by_id or by_id[dependency].status is not TaskStatus.COMPLETED
        ]
        if incomplete:
            return f"Dependencies were not completed: {', '.join(incomplete)}."
        return None

    @staticmethod
    def _task_summary(responses: list[AgentResponse]) -> str:
        if not responses:
            return "Task produced no response."
        return "Completed via " + ", ".join(response.agent_name for response in responses) + "."


__all__ = ["BoundedInvestigationGraph"]

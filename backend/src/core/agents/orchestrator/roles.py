"""The three reasoning roles used by the bounded orchestration graph."""

from __future__ import annotations

import re

from core.agents.base import AgentContext, BaseAgent
from core.agents.technical_agents.coverage_matching import CoverageMatchingAgent
from core.agents.technical_agents.exclusion_checking import ExclusionCheckingAgent
from core.agents.technical_agents.output_validator import OutputValidatorAgent
from core.models.agent import AgentResponse
from core.models.analysis import (
    InvestigationTask,
    InvestigationTaskType,
    PropositionStatus,
)


class CoverageAnalystAgent(BaseAgent):
    """Consumes a coverage task and resolves propositions from controlled evidence."""

    name = "CoverageAnalystAgent"

    def __init__(self) -> None:
        self._coverage_analysis = CoverageMatchingAgent()
        self._exclusion_analysis = ExclusionCheckingAgent()

    def run_task(
        self,
        context: AgentContext,
        task: InvestigationTask,
    ) -> list[AgentResponse]:
        target_ids = [str(item) for item in task.parameters.get("proposition_ids", [])]
        run_coverage = not target_ids or any(
            not item.startswith("exclusion-") for item in target_ids
        )
        run_exclusions = not target_ids or any(
            "exclusion" in item for item in target_ids
        )
        component_responses: list[AgentResponse] = []
        if run_coverage:
            coverage = self._coverage_analysis.run(context)
            context.add(coverage)
            component_responses.append(coverage)
        if run_exclusions:
            exclusions = self._exclusion_analysis.run(context)
            context.add(exclusions)
            component_responses.append(exclusions)
        proposition_ids = [item.proposition_id for item in context.propositions]
        component_confidence = [item.confidence for item in component_responses]
        response = self.respond(
            findings={
                "task_id": task.task_id,
                "coverage_assessment": context.memory.get("CoverageMatchingAgent", {}).get(
                    "coverage_assessment", "unclear"
                ),
                "potential_exclusions": context.memory.get("ExclusionCheckingAgent", {}).get(
                    "potential_exclusions", []
                ),
                "resolved_proposition_ids": proposition_ids,
                "target_proposition_ids": target_ids,
                "analysis_steps_run": [item.agent_name for item in component_responses],
                "selection_reason": task.selection_reason,
            },
            confidence=min(component_confidence) if component_confidence else 0.0,
            requires_human_review=any(item.requires_human_review for item in component_responses),
            messages=[
                self.message(
                    f"Resolved task {task.task_id} into {len(proposition_ids)} proposition(s).",
                    to_agent="EvidenceCriticAgent",
                    message_type="handoff",
                    metadata={
                        "task_id": task.task_id,
                        "proposition_ids": proposition_ids,
                        "selection_reason": task.selection_reason,
                    },
                )
            ],
        )
        return [*component_responses, response]

    def run(self, context: AgentContext) -> AgentResponse:
        task = InvestigationTask(
            task_id="compat-coverage-analysis",
            task_type=InvestigationTaskType.ANALYZE_COVERAGE,
            agent_name=self.name,
            assigned_role=self.name,
            objective="Analyze coverage for the current state.",
            selection_reason="Compatibility invocation requested coverage analysis.",
        )
        return self.run_task(context, task)[-1]


class EvidenceCriticAgent(BaseAgent):
    """Rejects unsupported propositions and emits proposition-targeted repair work."""

    name = "EvidenceCriticAgent"
    agent_type = "validator"

    _REPAIRABLE_MARKERS = (
        "not grounded",
        "no citation",
        "no exact cited passage",
        "supporting policy citation",
        "unknown policy clause",
    )

    def __init__(self) -> None:
        self._validator = OutputValidatorAgent()

    def run_task(
        self,
        context: AgentContext,
        task: InvestigationTask,
    ) -> tuple[list[AgentResponse], list[InvestigationTask]]:
        validation = self._validator.run(context)
        context.add(validation)
        proposition_validation = validation.findings.get("proposition_validation", {})
        rejected_ids = []
        for proposition in context.propositions:
            details = proposition_validation.get(proposition.proposition_id, {})
            if details and not details.get("valid", False):
                rejected_ids.append(proposition.proposition_id)
                # Preserve an already-inconclusive domain result; explicitly reject only a
                # proposition that claimed support without valid grounding.
                if proposition.status is PropositionStatus.SUPPORTED:
                    proposition.status = PropositionStatus.REJECTED

        feedback = validation.findings.get("feedback", [])
        repairable = [
            item
            for item in feedback
            if isinstance(item, dict)
            and any(marker in str(item.get("issue", "")).lower() for marker in self._REPAIRABLE_MARKERS)
        ]
        repair_tasks = self._repair_tasks(context, task, repairable, rejected_ids)
        coverage_gate_passed = bool(validation.findings.get("coverage_gate_passed"))
        if repair_tasks:
            verdict = "rejected"
        elif coverage_gate_passed and not feedback:
            verdict = "accepted"
        else:
            verdict = "uncertain"

        response = self.respond(
            findings={
                "task_id": task.task_id,
                "verdict": verdict,
                "coverage_gate_passed": coverage_gate_passed,
                "rejected_proposition_ids": rejected_ids,
                "feedback": feedback,
                "repair_requests": [item.model_dump(mode="json") for item in repair_tasks],
                "selection_reason": task.selection_reason,
            },
            confidence=validation.confidence,
            warnings=validation.warnings,
            requires_human_review=verdict != "accepted",
            messages=[
                self.message(
                    (
                        f"Critique {verdict}; requested {len(repair_tasks)} targeted task(s) "
                        f"for {len(rejected_ids)} rejected proposition(s)."
                    ),
                    to_agent="InvestigationPlannerAgent",
                    message_type="request" if repair_tasks else "validation",
                    metadata={
                        "source_task_id": task.task_id,
                        "verdict": verdict,
                        "rejected_proposition_ids": rejected_ids,
                        "repair_task_ids": [item.task_id for item in repair_tasks],
                    },
                )
            ],
        )
        return [validation, response], repair_tasks

    def run(self, context: AgentContext) -> AgentResponse:
        task = InvestigationTask(
            task_id="compat-evidence-critique",
            task_type=InvestigationTaskType.CRITIQUE_EVIDENCE,
            agent_name=self.name,
            assigned_role=self.name,
            objective="Critique the current evidence state.",
            selection_reason="Compatibility invocation requested evidence critique.",
        )
        return self.run_task(context, task)[0][-1]

    def _repair_tasks(
        self,
        context: AgentContext,
        source_task: InvestigationTask,
        feedback: list[dict],
        rejected_ids: list[str],
    ) -> list[InvestigationTask]:
        if not feedback or not context.request.policy_text.strip():
            return []
        proposition_ids = list(dict.fromkeys([*rejected_ids, *self._feedback_ids(feedback)]))
        statements = [
            proposition.statement
            for proposition in context.propositions
            if proposition.proposition_id in proposition_ids
        ]
        issue_text = " ".join(str(item.get("issue", "")) for item in feedback)
        query = " ".join([*statements, issue_text, context.request.claim_description]).strip()
        iteration = context.usage.repair_iterations + 1
        prefix = f"repair-{iteration}"
        targeted_analysis_calls = self._targeted_analysis_calls(proposition_ids)
        common = {
            "parent_task_id": source_task.task_id,
            "attempt": iteration,
        }
        return [
            InvestigationTask(
                task_id=f"{prefix}-retrieve",
                task_type=InvestigationTaskType.RETRIEVE_EVIDENCE,
                agent_name="RetrievalAgent",
                assigned_role="InvestigationPlannerAgent",
                tool_name="RetrievalAgent",
                objective="Retrieve exact evidence for the rejected propositions only.",
                selection_reason=(
                    "The critic rejected proposition grounding and requested exact corresponding passages."
                ),
                parameters={"query": query[:4000], "proposition_ids": proposition_ids},
                **common,
            ),
            InvestigationTask(
                task_id=f"{prefix}-reanalyze",
                task_type=InvestigationTaskType.ANALYZE_COVERAGE,
                agent_name="CoverageAnalystAgent",
                assigned_role="CoverageAnalystAgent",
                objective="Re-analyze only the propositions rejected by the critic.",
                selection_reason="New targeted retrieval may change the rejected coverage propositions.",
                depends_on=[f"{prefix}-retrieve"],
                parameters={"proposition_ids": proposition_ids},
                expected_model_calls=targeted_analysis_calls,
                estimated_cost_usd=0.003 * targeted_analysis_calls,
                **common,
            ),
            InvestigationTask(
                task_id=f"{prefix}-cite",
                task_type=InvestigationTaskType.FORMAT_CITATIONS,
                agent_name="CitationAgent",
                assigned_role="InvestigationPlannerAgent",
                tool_name="CitationAgent",
                objective="Attach exact citations to the re-analyzed propositions.",
                selection_reason="Re-analyzed propositions must be cited before another critique.",
                depends_on=[f"{prefix}-reanalyze"],
                parameters={"proposition_ids": proposition_ids},
                **common,
            ),
            InvestigationTask(
                task_id=f"{prefix}-critique",
                task_type=InvestigationTaskType.CRITIQUE_EVIDENCE,
                agent_name=self.name,
                assigned_role=self.name,
                objective="Re-check the targeted repaired propositions.",
                selection_reason="A bounded repair must be independently accepted or rejected.",
                depends_on=[f"{prefix}-cite"],
                parameters={"proposition_ids": proposition_ids},
                **common,
            ),
        ]

    @staticmethod
    def _feedback_ids(feedback: list[dict]) -> list[str]:
        ids: list[str] = []
        for item in feedback:
            match = re.search(r"Proposition ([\w-]+)", str(item.get("issue", "")))
            if match:
                ids.append(match.group(1))
        return ids

    @staticmethod
    def _targeted_analysis_calls(proposition_ids: list[str]) -> int:
        coverage = any(not item.startswith("exclusion-") for item in proposition_ids)
        exclusions = any("exclusion" in item for item in proposition_ids)
        return int(coverage) + int(exclusions) or 1


__all__ = ["CoverageAnalystAgent", "EvidenceCriticAgent"]

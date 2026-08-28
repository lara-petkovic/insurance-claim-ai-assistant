"""Allow-listed deterministic and model-backed services used by the execution graph."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from core.agents.base import AgentContext, BaseAgent
from core.agents.functional_agents import (
    AutoInsuranceFunctionalAgent,
    GeneralInsuranceFunctionalAgent,
    HomeInsuranceFunctionalAgent,
    TravelInsuranceFunctionalAgent,
)
from core.agents.orchestrator.synthesis import FinalDecisionSynthesisAgent
from core.agents.technical_agents import (
    CitationAgent,
    ClaimExtractionAgent,
    ConsistencyVerificationAgent,
    DocumentIngestionAgent,
    DocumentQualityAgent,
    ImageAuthenticityAgent,
    MissingDocumentsAgent,
    PolicyConceptExtractionAgent,
    QueryRewriteAgent,
    RetrievalAgent,
    VisualEvidenceAgent,
)
from core.agents.technical_agents.shared import specialized_functional_agent_name
from core.models.agent import AgentMessage, AgentResponse
from core.models.analysis import GenericAgentFindings, InvestigationTask, InvestigationTaskType


@dataclass(frozen=True)
class ServiceSpec:
    task_type: InvestigationTaskType
    service_name: str
    execute: Callable[[AgentContext, InvestigationTask], list[AgentResponse]]


class SettlementCalculationService:
    """Parses explicit amounts and computes only arithmetic that the inputs support."""

    name = "SettlementCalculationService"

    @staticmethod
    def run(context: AgentContext, task: InvestigationTask) -> AgentResponse:
        claim_amount = SettlementCalculationService._number(
            context.memory.get("ClaimExtractionAgent", {}).get("claimed_amount")
        )
        deductible = SettlementCalculationService._number(
            context.memory.get("PolicyConceptExtractionAgent", {}).get("deductible_or_excess")
        )
        payable = max(0.0, claim_amount - deductible) if claim_amount is not None and deductible is not None else None
        return AgentResponse(
            agent_name=SettlementCalculationService.name,
            findings=GenericAgentFindings.model_validate(
                {
                    "claimed_amount": claim_amount,
                    "deductible_or_excess": deductible,
                    "estimated_payable_before_limits": payable,
                    "calculation_performed": payable is not None,
                    "task_id": task.task_id,
                }
            ),
            confidence=0.95 if payable is not None else 0.0,
            warnings=[] if payable is not None else ["No supported settlement arithmetic was available."],
            requires_human_review=payable is None,
        )

    @staticmethod
    def _number(value: object) -> float | None:
        if value is None:
            return None
        match = re.search(r"-?\d[\d,.]*", str(value))
        if not match:
            return None
        normalized = match.group(0).replace(",", "")
        try:
            return float(normalized)
        except ValueError:
            return None


class ControlledServiceRegistry:
    """Executes only services explicitly mapped to typed investigation tasks."""

    def __init__(self) -> None:
        self._agents: dict[InvestigationTaskType, BaseAgent] = {
            InvestigationTaskType.INGEST_DOCUMENTS: DocumentIngestionAgent(),
            InvestigationTaskType.CHECK_DOCUMENT_QUALITY: DocumentQualityAgent(),
            InvestigationTaskType.EXTRACT_POLICY: PolicyConceptExtractionAgent(),
            InvestigationTaskType.EXTRACT_CLAIM: ClaimExtractionAgent(),
            InvestigationTaskType.REWRITE_QUERY: QueryRewriteAgent(),
            InvestigationTaskType.RETRIEVE_EVIDENCE: RetrievalAgent(),
            InvestigationTaskType.ANALYZE_IMAGE: VisualEvidenceAgent(),
            InvestigationTaskType.CHECK_IMAGE_AUTHENTICITY: ImageAuthenticityAgent(),
            InvestigationTaskType.CHECK_DOCUMENTS: MissingDocumentsAgent(),
            InvestigationTaskType.CHECK_CONSISTENCY: ConsistencyVerificationAgent(),
            InvestigationTaskType.FORMAT_CITATIONS: CitationAgent(),
            InvestigationTaskType.SYNTHESIZE: FinalDecisionSynthesisAgent(),
        }
        self._functional_agents: dict[str, BaseAgent] = {
            agent.name: agent
            for agent in (
                GeneralInsuranceFunctionalAgent(),
                HomeInsuranceFunctionalAgent(),
                AutoInsuranceFunctionalAgent(),
                TravelInsuranceFunctionalAgent(),
            )
        }

    def execute(self, context: AgentContext, task: InvestigationTask) -> list[AgentResponse]:
        if task.task_type is InvestigationTaskType.LOAD_DOMAIN_GUIDANCE:
            names = ["GeneralInsuranceFunctionalAgent", specialized_functional_agent_name(context.request.insurance_type)]
            return [self._with_task_metadata(agent.run(context), task) for name in names if (agent := self._functional_agents.get(name))]
        if task.task_type is InvestigationTaskType.CALCULATE_SETTLEMENT:
            return [self._with_task_metadata(SettlementCalculationService.run(context, task), task)]
        agent = self._agents.get(task.task_type)
        if agent is None:
            raise ValueError(f"No controlled service is registered for task type {task.task_type}.")
        if task.task_type is InvestigationTaskType.RETRIEVE_EVIDENCE:
            self._apply_targeted_query(context, task)
        return [self._with_task_metadata(agent.run(context), task)]

    @staticmethod
    def _apply_targeted_query(context: AgentContext, task: InvestigationTask) -> None:
        query = task.parameters.get("query")
        if not query:
            return
        current = context.memory.get("QueryRewriteAgent", GenericAgentFindings())
        data = current.model_dump(mode="python")
        data.update(
            {
                "rewritten_query": str(query),
                "target_proposition_ids": task.parameters.get("proposition_ids", []),
                "repair_task_id": task.task_id,
            }
        )
        context.memory["QueryRewriteAgent"] = GenericAgentFindings.model_validate(data)

    @staticmethod
    def _with_task_metadata(response: AgentResponse, task: InvestigationTask) -> AgentResponse:
        response.messages.append(
            AgentMessage(
                from_agent=response.agent_name,
                to_agent=task.assigned_role,
                message_type="response",
                content=f"Executed task {task.task_id}: {task.objective}",
                metadata={
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "selection_reason": task.selection_reason,
                    "parameters": task.parameters,
                },
            )
        )
        return response


__all__ = ["ControlledServiceRegistry", "SettlementCalculationService"]

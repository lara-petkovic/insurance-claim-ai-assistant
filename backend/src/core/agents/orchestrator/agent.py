from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from core.agents.base import AgentContext, BaseAgent
from core.agents.orchestrator.graph import BoundedInvestigationGraph
from core.agents.orchestrator.streaming import StreamingProgressCompatibilityAdapter
from core.models.agent import AgentResponse
from core.models.analysis import OrchestrationLimits, OrchestrationStopReason
from core.models.claim import (
    ClaimAnalysisResult,
    ClaimRequestData,
    ClaimStatus,
    CoverageAssessment,
    ImageAssessment,
    ImageAuthenticity,
    OrchestrationSummary,
    RiskLevel,
)
from utils.app_logger import get_logger, log_event


def _log_agent_activity(agent_name: str, message: str, **details: Any) -> None:
    log_event(get_logger(f"agents.{agent_name}"), message, **details)


def _log_agent_messages(response: AgentResponse) -> None:
    for message in response.messages:
        if not message.to_agent:
            continue
        _log_agent_activity(
            message.from_agent or response.agent_name,
            "Message emitted.",
            from_agent=message.from_agent,
            to_agent=message.to_agent,
            message_type=message.message_type,
            content=message.content,
        )


def _log_agent_completed(response: AgentResponse, **details: Any) -> None:
    _log_agent_activity(
        response.agent_name,
        "Completed.",
        status=response.status,
        confidence=response.confidence,
        evidence=len(response.evidence),
        warnings=len(response.warnings),
        human_review=response.requires_human_review,
        **details,
    )


class OrchestratorAgent(BaseAgent):
    """API facade over the explicit bounded investigation graph."""

    name = "OrchestratorAgent"
    agent_type = "orchestrator"

    def __init__(
        self,
        *,
        limits: OrchestrationLimits | None = None,
        graph: BoundedInvestigationGraph | None = None,
    ) -> None:
        self.limits = limits or OrchestrationLimits()
        self.graph = graph or BoundedInvestigationGraph()
        self.planner = self.graph.planner
        self.agents = [self.graph.planner, self.graph.analyst, self.graph.critic]
        self.last_run_state: AgentContext | None = None

    def run(self, context: AgentContext) -> AgentResponse:
        context.limits = self.limits.model_copy(deep=True)
        self.last_run_state = context
        for event in self.graph.execute(context):
            for response in event.get("responses", []):
                _log_agent_messages(response)
                _log_agent_completed(response, task_id=event.get("task", {}).task_id if event.get("task") else None)
        _log_agent_activity(
            self.name,
            "Analysis completed.",
            completed_agents=len(context.responses),
            stop_reason=context.stop_reason,
            model_calls=context.usage.model_calls,
            repair_iterations=context.usage.repair_iterations,
        )
        return self.respond(
            findings={
                "completed_agents": [response.agent_name for response in context.responses],
                "inter_agent_messages": [message.model_dump(mode="json") for message in context.messages],
                "stop_reason": context.stop_reason,
                "stop_detail": context.stop_detail,
                "usage": context.usage.model_dump(mode="json"),
                "actions": [action.model_dump(mode="json") for action in context.actions],
            },
            confidence=0.9,
            requires_human_review=context.stop_reason is not OrchestrationStopReason.SUFFICIENT_EVIDENCE,
            messages=[
                self.message(
                    f"Bounded execution stopped with {context.stop_reason}.",
                    message_type="summary",
                    metadata={
                        "stop_reason": context.stop_reason,
                        "stop_detail": context.stop_detail,
                        "message_count": len(context.messages),
                    },
                )
            ],
        )

    def stream(self, request: ClaimRequestData) -> Iterator[dict[str, Any]]:
        context = AgentContext(request=request, limits=self.limits.model_copy(deep=True))
        self.last_run_state = context
        adapter = StreamingProgressCompatibilityAdapter()
        for graph_event in self.graph.execute(context):
            for event in adapter.adapt(graph_event, context):
                yield event
        result = self._result_from_context(request, context)
        _log_agent_activity(
            self.name,
            "Streaming analysis completed.",
            claim_status=result.claim_status,
            coverage=result.coverage_assessment,
            claim_type=result.claim_type,
        )
        yield {
            "event": "analysis_completed",
            "message": "Agent analysis completed.",
            "result": result.model_dump(mode="json"),
            "orchestration": {
                "stop_reason": context.stop_reason,
                "stop_detail": context.stop_detail,
                "usage": context.usage.model_dump(mode="json"),
            },
        }

    def analyze(self, request: ClaimRequestData) -> ClaimAnalysisResult:
        context = AgentContext(request=request, limits=self.limits.model_copy(deep=True))
        self.run(context)
        return self._result_from_context(request, context)

    def _result_from_context(self, request: ClaimRequestData, context: AgentContext) -> ClaimAnalysisResult:
        claim = context.memory.get("ClaimExtractionAgent", {})
        coverage = context.memory.get("CoverageMatchingAgent", {})
        exclusions = self._as_dict_list(context.memory.get("ExclusionCheckingAgent", {}).get("potential_exclusions", []), default_key="concept")
        missing_docs = context.memory.get("MissingDocumentsAgent", {}).get("missing_documents", [])
        consistency = context.memory.get("ConsistencyVerificationAgent", {}).get("consistency_issues", [])
        visual_findings = dict(context.memory.get("VisualEvidenceAgent", {}))
        visual_findings["notes"] = self._as_text_list(visual_findings.get("notes"))
        authenticity_findings = dict(context.memory.get("ImageAuthenticityAgent", {}))
        authenticity_findings["signals"] = self._as_text_list(authenticity_findings.get("signals"))
        image_assessment = ImageAssessment(**visual_findings)
        image_authenticity = ImageAuthenticity(**authenticity_findings)
        citations = []
        for response in context.responses:
            if response.agent_name == "CitationAgent":
                citations = response.evidence

        validated_coverage = context.memory.get("OutputValidatorAgent", {}).get(
            "validated_coverage_assessment", coverage.get("coverage_assessment", "unclear")
        )
        coverage_assessment = self._coverage_assessment(validated_coverage)
        validator_feedback = context.memory.get("OutputValidatorAgent", {}).get("feedback", [])
        if coverage_assessment == "covered" and any(
            "no relevant supporting policy citation" in str(item.get("issue", "")).lower()
            for item in validator_feedback
            if isinstance(item, dict)
        ):
            coverage_assessment = CoverageAssessment.UNCLEAR
        requires_review = (
            bool(request.security_flags)
            or context.stop_reason is not OrchestrationStopReason.SUFFICIENT_EVIDENCE
            or any(response.requires_human_review for response in context.responses)
        )

        claim_status: ClaimStatus
        if request.security_flags:
            claim_status = ClaimStatus.REQUIRES_HUMAN_REVIEW
        elif exclusions and any(item.get("severity") == "high" for item in exclusions):
            claim_status = ClaimStatus.LIKELY_NOT_COVERED
        elif coverage_assessment == "covered" and not requires_review and not missing_docs and not exclusions and image_authenticity.risk_level in {RiskLevel.LOW, RiskLevel.MEDIUM}:
            claim_status = ClaimStatus.LIKELY_COVERED
        elif coverage_assessment == "covered" and (requires_review or missing_docs or exclusions or consistency):
            claim_status = ClaimStatus.REQUIRES_HUMAN_REVIEW
        elif coverage_assessment == "possibly_covered":
            claim_status = ClaimStatus.REQUIRES_HUMAN_REVIEW
        elif coverage_assessment == "unclear" and requires_review:
            claim_status = ClaimStatus.REQUIRES_HUMAN_REVIEW
        else:
            claim_status = ClaimStatus.LIKELY_NOT_COVERED

        reasoning_summary = self._build_reasoning(
            claim_type=claim.get("claim_type", "unknown"),
            coverage_assessment=coverage_assessment,
            exclusions=exclusions,
            missing_docs=missing_docs,
            consistency=consistency,
            image_authenticity=image_authenticity,
        )
        recommendation = self._build_recommendation(claim_status)
        synthesis = context.memory.get("FinalDecisionSynthesisAgent", {})
        if synthesis.get("review_reasons"):
            reasoning_summary += f" Final synthesis flagged: {', '.join(synthesis.get('review_reasons', []))}."
        if context.stop_reason is not None:
            reasoning_summary += (
                f" Orchestration stopped because {context.stop_reason.value}: "
                f"{context.stop_detail or 'no additional detail'}"
            )

        return ClaimAnalysisResult(
            claim_status=claim_status,
            insurance_type=request.insurance_type,
            claim_type=claim.get("claim_type", "unknown"),
            coverage_assessment=coverage_assessment,
            matched_policy_concepts=self._as_dict_list(coverage.get("matched_policy_concepts", []), default_key="concept"),
            potential_exclusions=exclusions,
            missing_documents=missing_docs,
            image_assessment=image_assessment,
            image_authenticity=image_authenticity,
            evidence=citations,
            claim_facts=claim.get("facts", []),
            policy_clauses=context.memory.get("PolicyConceptExtractionAgent", {}).get(
                "policy_clauses",
                context.memory.get("PolicyConceptExtractionAgent", {}).get("coverage_clauses", []),
            ),
            assessment_propositions=sorted(
                context.propositions,
                key=lambda item: (
                    item.created_by == "CoverageMatchingAgent",
                    item.proposition_type == "coverage",
                ),
            ),
            reasoning_summary=reasoning_summary,
            recommendation=recommendation,
            security_flags=request.security_flags,
            orchestration=OrchestrationSummary(
                stop_reason=context.stop_reason,
                stop_detail=context.stop_detail,
                usage=context.usage,
                actions=context.actions,
            ),
            agent_trace=context.responses,
        )

    @staticmethod
    def _build_reasoning(
        claim_type: str,
        coverage_assessment: CoverageAssessment,
        exclusions: list[dict],
        missing_docs: list[str],
        consistency: list[str],
        image_authenticity: ImageAuthenticity,
    ) -> str:
        parts = [
            f"The claim was classified as {claim_type}.",
            f"Policy concept matching returned {coverage_assessment}.",
        ]
        if exclusions:
            parts.append(f"Potential exclusions were detected: {', '.join(item.get('concept', 'unknown') for item in exclusions)}.")
        if missing_docs:
            parts.append(f"The claim package is missing: {', '.join(missing_docs)}.")
        if consistency:
            parts.append(f"Consistency issues were found: {'; '.join(consistency)}")
        parts.append(f"Image authenticity risk is {image_authenticity.risk_level} with score {image_authenticity.risk_score}.")
        parts.append("This is a preliminary explainable opinion, not a final insurance decision.")
        return " ".join(parts)

    @staticmethod
    def _build_recommendation(status: ClaimStatus) -> str:
        if status is ClaimStatus.LIKELY_COVERED:
            return "Proceed with adjuster review and payment workflow after verifying original documents."
        if status is ClaimStatus.LIKELY_NOT_COVERED:
            return "Send to human adjuster with highlighted exclusions before any denial decision."
        if status is ClaimStatus.PARTIALLY_COVERED:
            return "Send to human adjuster to separate covered and non-covered components."
        return "Send to human adjuster with highlighted evidence, missing documents, and risk flags."

    @staticmethod
    def _coverage_assessment(value: object) -> CoverageAssessment:
        try:
            return CoverageAssessment(str(value))
        except ValueError:
            return CoverageAssessment.UNCLEAR

    @staticmethod
    def _as_text_list(value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @classmethod
    def _as_dict_list(cls, value: object, *, default_key: str) -> list[dict]:
        normalized = []
        for item in cls._as_any_list(value):
            if isinstance(item, dict):
                normalized.append(item)
            elif hasattr(item, "model_dump"):
                normalized.append(item.model_dump(mode="json"))
            else:
                normalized.append({default_key: str(item)})
        return normalized

    @staticmethod
    def _as_any_list(value: object) -> list:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from core.agents.base import AgentContext, BaseAgent
from core.agents.functional_agents import (
    AutoInsuranceFunctionalAgent,
    GeneralInsuranceFunctionalAgent,
    HomeInsuranceFunctionalAgent,
    TravelInsuranceFunctionalAgent,
)
from core.agents.orchestrator.planning import DynamicPlanningAgent
from core.agents.orchestrator.synthesis import FinalDecisionSynthesisAgent
from core.agents.technical_agents import (
    CitationAgent,
    ClaimExtractionAgent,
    ConsistencyVerificationAgent,
    CoverageMatchingAgent,
    DocumentIngestionAgent,
    DocumentQualityAgent,
    ExclusionCheckingAgent,
    ImageAuthenticityAgent,
    MissingDocumentsAgent,
    OutputValidatorAgent,
    PolicyConceptExtractionAgent,
    QueryRewriteAgent,
    RetrievalAgent,
    VisualEvidenceAgent,
)
from core.models.agent import AgentResponse
from core.models.claim import (
    ClaimAnalysisResult,
    ClaimRequestData,
    ClaimStatus,
    CoverageAssessment,
    ImageAssessment,
    ImageAuthenticity,
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
    """Coordinates the agent team, shared memory, streaming events, and feedback repairs."""

    name = "OrchestratorAgent"
    agent_type = "orchestrator"

    def __init__(self) -> None:
        self.planner = DynamicPlanningAgent()
        self.agent_registry: dict[str, BaseAgent] = {
            agent.name: agent
            for agent in [
                DocumentIngestionAgent(),
                DocumentQualityAgent(),
                PolicyConceptExtractionAgent(),
                ClaimExtractionAgent(),
                GeneralInsuranceFunctionalAgent(),
                HomeInsuranceFunctionalAgent(),
                AutoInsuranceFunctionalAgent(),
                TravelInsuranceFunctionalAgent(),
                QueryRewriteAgent(),
                RetrievalAgent(),
                VisualEvidenceAgent(),
                ImageAuthenticityAgent(),
                CoverageMatchingAgent(),
                ExclusionCheckingAgent(),
                MissingDocumentsAgent(),
                ConsistencyVerificationAgent(),
                CitationAgent(),
                OutputValidatorAgent(),
                FinalDecisionSynthesisAgent(),
            ]
        }
        self.agents: list[BaseAgent] = list(self.agent_registry.values())

    def run(self, context: AgentContext) -> AgentResponse:
        _log_agent_activity(self.planner.name, "Started.", step="planning")
        plan_response = context.add(self.planner.run(context))
        planned_agents = self._agents_from_plan(plan_response)
        _log_agent_messages(plan_response)
        _log_agent_completed(plan_response, planned_agents=len(planned_agents))
        _log_agent_activity(
            self.name,
            "Analysis started.",
            agents=len(planned_agents),
            insurance_type=context.request.insurance_type,
            policy_chars=len(context.request.policy_text or ""),
            has_image=bool(context.request.damage_image_filename),
        )
        for index, agent in enumerate(planned_agents, start=1):
            _log_agent_activity(agent.name, "Started.", step=f"{index}/{len(planned_agents)}")
            response = context.add(agent.run(context))
            _log_agent_messages(response)
            if agent.name == "OutputValidatorAgent":
                self._run_feedback_repairs(context)
            _log_agent_completed(response)
        _log_agent_activity(self.name, "Analysis completed.", completed_agents=len(context.responses))
        return self.respond(
            findings={
                "completed_agents": [agent.name for agent in planned_agents],
                "inter_agent_messages": [message.model_dump(mode="json") for message in context.messages],
                "dynamic_plan": plan_response.findings,
            },
            confidence=0.9,
            messages=[
                self.message(
                    "Agentic team completed dynamic planned execution with shared memory and explicit inter-agent messages.",
                    message_type="summary",
                    metadata={"completed_agents": [agent.name for agent in planned_agents], "message_count": len(context.messages)},
                )
            ],
        )

    def stream(self, request: ClaimRequestData) -> Iterator[dict[str, Any]]:
        context = AgentContext(request=request)
        _log_agent_activity(self.planner.name, "Started.", step="planning")
        plan_response = context.add(self.planner.run(context))
        planned_agents = self._agents_from_plan(plan_response)
        total = len(planned_agents)
        _log_agent_messages(plan_response)
        _log_agent_completed(plan_response, planned_agents=total)
        _log_agent_activity(
            self.name,
            "Streaming analysis started.",
            agents=total,
            insurance_type=request.insurance_type,
            policy_chars=len(request.policy_text or ""),
            has_image=bool(request.damage_image_filename),
        )
        yield {
            "event": "analysis_started",
            "total_agents": total,
            "message": "Dynamic agent analysis started.",
            "agent_response": plan_response.model_dump(mode="json"),
            "planned_agents": [agent.name for agent in planned_agents],
        }
        yield {
            "event": "agent_completed",
            "agent_name": self.planner.name,
            "index": 0,
            "total_agents": total,
            "message": f"{self.planner.name} completed.",
            "agent_response": plan_response.model_dump(mode="json"),
        }
        for index, agent in enumerate(planned_agents, start=1):
            yield {
                "event": "agent_started",
                "agent_name": agent.name,
                "index": index,
                "total_agents": total,
                "message": f"{agent.name} started.",
            }
            _log_agent_activity(agent.name, "Started.", step=f"{index}/{total}")
            response = context.add(agent.run(context))
            _log_agent_messages(response)
            repair_responses = []
            if agent.name == "OutputValidatorAgent":
                repair_responses = self._run_feedback_repairs(context)
            _log_agent_completed(response)
            yield {
                "event": "agent_completed",
                "agent_name": agent.name,
                "index": index,
                "total_agents": total,
                "message": f"{agent.name} completed.",
                "agent_response": response.model_dump(mode="json"),
            }
            for repair_response in repair_responses:
                yield {
                    "event": "agent_completed",
                    "agent_name": repair_response.agent_name,
                    "index": index,
                    "total_agents": total,
                    "message": f"{repair_response.agent_name} repaired from validator feedback.",
                    "agent_response": repair_response.model_dump(mode="json"),
                }
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
        }

    def analyze(self, request: ClaimRequestData) -> ClaimAnalysisResult:
        context = AgentContext(request=request)
        self.run(context)
        return self._result_from_context(request, context)

    def _agents_from_plan(self, plan_response: AgentResponse) -> list[BaseAgent]:
        names = plan_response.findings.get("planned_agents", [])
        agents = [self.agent_registry[name] for name in names if isinstance(name, str) and name in self.agent_registry]
        return agents or list(self.agent_registry.values())

    def _run_feedback_repairs(self, context: AgentContext) -> list[AgentResponse]:
        feedback = context.memory.get("OutputValidatorAgent", {}).get("feedback", [])
        if not feedback:
            return []

        repair_targets: list[str] = []
        for item in feedback:
            if not isinstance(item, dict):
                continue
            issue = str(item.get("issue", "")).lower()
            target = str(item.get("target_agent", ""))
            if "no citation" in issue or "no citation is available" in issue:
                repair_targets.extend(["QueryRewriteAgent", "RetrievalAgent", "CoverageMatchingAgent", "CitationAgent"])
            elif target in {"CoverageMatchingAgent", "RetrievalAgent"}:
                repair_targets.append(target)

        ordered_unique = []
        for target in repair_targets:
            if target in self.agent_registry and target not in ordered_unique:
                ordered_unique.append(target)

        repair_responses = []
        for target in ordered_unique[:4]:
            agent = self.agent_registry[target]
            _log_agent_activity(agent.name, "Started.", step="validator-repair")
            response = agent.run(context)
            response.messages.append(
                self.message(
                    f"{target} reran after validator feedback.",
                    to_agent="OutputValidatorAgent",
                    message_type="feedback",
                    metadata={"repair_target": target},
                )
            )
            response = context.replace(response)
            _log_agent_messages(response)
            _log_agent_completed(response, step="validator-repair")
            repair_responses.append(response)

        if repair_responses:
            validator = self.agent_registry["OutputValidatorAgent"]
            _log_agent_activity(validator.name, "Started.", step="validator-recheck")
            validator_response = context.replace(validator.run(context))
            _log_agent_messages(validator_response)
            _log_agent_completed(validator_response, step="validator-recheck")
            repair_responses.append(validator_response)

        return repair_responses

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

        coverage_assessment = self._coverage_assessment(coverage.get("coverage_assessment", "unclear"))
        requires_review = any(response.requires_human_review for response in context.responses)

        claim_status: ClaimStatus
        if exclusions and any(item.get("severity") == "high" for item in exclusions):
            claim_status = "likely_not_covered"
        elif coverage_assessment == "covered" and not missing_docs and not exclusions and image_authenticity.risk_level in {"low", "medium"}:
            claim_status = "likely_covered"
        elif coverage_assessment == "covered" and (missing_docs or exclusions or consistency):
            claim_status = "requires_human_review"
        elif coverage_assessment == "possibly_covered":
            claim_status = "requires_human_review"
        elif coverage_assessment == "unclear" and requires_review:
            claim_status = "requires_human_review"
        else:
            claim_status = "likely_not_covered"

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
            reasoning_summary=reasoning_summary,
            recommendation=recommendation,
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
        if status == "likely_covered":
            return "Proceed with adjuster review and payment workflow after verifying original documents."
        if status == "likely_not_covered":
            return "Send to human adjuster with highlighted exclusions before any denial decision."
        if status == "partially_covered":
            return "Send to human adjuster to separate covered and non-covered components."
        return "Send to human adjuster with highlighted evidence, missing documents, and risk flags."

    @staticmethod
    def _coverage_assessment(value: object) -> CoverageAssessment:
        if value == "covered":
            return "covered"
        if value == "not_covered":
            return "not_covered"
        if value == "possibly_covered":
            return "possibly_covered"
        return "unclear"

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

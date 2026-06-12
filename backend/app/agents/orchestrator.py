from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.agents.base import AgentContext, BaseAgent
from app.agents.functional import GeneralInsuranceFunctionalAgent, HomeInsuranceFunctionalAgent
from app.agents.technical import (
    CitationAgent,
    ClaimExtractionAgent,
    ConsistencyVerificationAgent,
    CoverageMatchingAgent,
    DocumentIngestionAgent,
    ExclusionCheckingAgent,
    ImageAuthenticityAgent,
    MissingDocumentsAgent,
    OutputValidatorAgent,
    PolicyConceptExtractionAgent,
    RetrievalAgent,
    VisualEvidenceAgent,
)
from app.schemas.agent import AgentResponse
from app.schemas.claim import ClaimAnalysisResult, ClaimRequestData, ImageAssessment, ImageAuthenticity
from app.services.agent_logger import log_agent_event


class OrchestratorAgent(BaseAgent):
    name = "OrchestratorAgent"

    def __init__(self) -> None:
        self.agents: list[BaseAgent] = [
            DocumentIngestionAgent(),
            PolicyConceptExtractionAgent(),
            ClaimExtractionAgent(),
            GeneralInsuranceFunctionalAgent(),
            HomeInsuranceFunctionalAgent(),
            RetrievalAgent(),
            VisualEvidenceAgent(),
            ImageAuthenticityAgent(),
            CoverageMatchingAgent(),
            ExclusionCheckingAgent(),
            MissingDocumentsAgent(),
            ConsistencyVerificationAgent(),
            CitationAgent(),
            OutputValidatorAgent(),
        ]

    def run(self, context: AgentContext) -> AgentResponse:
        log_agent_event(
            self.name,
            "Analysis started.",
            agents=len(self.agents),
            insurance_type=context.request.insurance_type,
            policy_chars=len(context.request.policy_text or ""),
            has_image=bool(context.request.damage_image_filename),
        )
        for index, agent in enumerate(self.agents, start=1):
            log_agent_event(agent.name, "Started.", step=f"{index}/{len(self.agents)}")
            response = context.add(agent.run(context))
            log_agent_event(
                agent.name,
                "Completed.",
                status=response.status,
                confidence=response.confidence,
                evidence=len(response.evidence),
                warnings=len(response.warnings),
                human_review=response.requires_human_review,
            )
        log_agent_event(self.name, "Analysis completed.", completed_agents=len(context.responses))
        return AgentResponse(
            agent_name=self.name,
            findings={"completed_agents": [agent.name for agent in self.agents]},
            confidence=0.9,
        )

    def stream(self, request: ClaimRequestData) -> Iterator[dict[str, Any]]:
        context = AgentContext(request=request)
        total = len(self.agents)
        log_agent_event(
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
            "message": "Agent analysis started.",
        }
        for index, agent in enumerate(self.agents, start=1):
            yield {
                "event": "agent_started",
                "agent_name": agent.name,
                "index": index,
                "total_agents": total,
                "message": f"{agent.name} started.",
            }
            log_agent_event(agent.name, "Started.", step=f"{index}/{total}")
            response = context.add(agent.run(context))
            log_agent_event(
                agent.name,
                "Completed.",
                status=response.status,
                confidence=response.confidence,
                evidence=len(response.evidence),
                warnings=len(response.warnings),
                human_review=response.requires_human_review,
            )
            yield {
                "event": "agent_completed",
                "agent_name": agent.name,
                "index": index,
                "total_agents": total,
                "message": f"{agent.name} completed.",
                "agent_response": response.model_dump(mode="json"),
            }
        result = self._result_from_context(request, context)
        log_agent_event(
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

        coverage_assessment = coverage.get("coverage_assessment", "unclear")
        requires_review = any(response.requires_human_review for response in context.responses)

        if exclusions and any(item.get("severity") == "high" for item in exclusions):
            claim_status = "likely_not_covered"
        elif coverage_assessment == "covered" and not missing_docs and not exclusions and image_authenticity.risk_level in {"low", "medium"}:
            claim_status = "likely_covered"
        elif coverage_assessment == "covered" and (missing_docs or consistency):
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
        coverage_assessment: str,
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
    def _build_recommendation(status: str) -> str:
        if status == "likely_covered":
            return "Proceed with adjuster review and payment workflow after verifying original documents."
        if status == "likely_not_covered":
            return "Send to human adjuster with highlighted exclusions before any denial decision."
        if status == "partially_covered":
            return "Send to human adjuster to separate covered and non-covered components."
        return "Send to human adjuster with highlighted evidence, missing documents, and risk flags."

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

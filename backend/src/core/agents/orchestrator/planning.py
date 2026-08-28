from __future__ import annotations

from typing import Any

from core.agents.base import AgentContext, BaseAgent
from core.agents.constants import (
    CLAIM_THEME_CONFIG,
    UNKNOWN_THEME,
    UNKNOWN_THEME_RATIONALE,
)
from core.agents.technical_agents.shared import specialized_functional_agent_name
from core.models.agent import AgentResponse
from core.models.analysis import (
    DynamicPlanningFindings,
    InvestigationTask,
    InvestigationTaskType,
    PlanningSignalsFindings,
    PlanningSignalsModelOutput,
)
from models.model_client import get_model_client
from utils.app_logger import get_logger, log_event

logger = get_logger("agents.DynamicPlanningAgent")


class InvestigationPlannerAgent(BaseAgent):
    """Creates typed work from the unresolved evidence state."""

    name = "InvestigationPlannerAgent"
    agent_type = "orchestrator"

    def run(self, context: AgentContext) -> AgentResponse:
        log_event(
            logger,
            "Planning decision started.",
            insurance_type=context.request.insurance_type,
            claim_chars=len(context.request.claim_description or ""),
            policy_chars=len(context.request.policy_text or ""),
            has_image=bool(context.request.damage_image_bytes or context.request.damage_image_filename),
        )
        functional_agent = specialized_functional_agent_name(context.request.insurance_type)
        planning_signals = self._planning_signals(context)
        tasks = self.create_tasks(context, planning_signals)
        planned_agents = self._legacy_plan(tasks, functional_agent)
        rationale = [
            "Typed tasks were selected from unresolved facts and the evidence actually supplied.",
            f"{functional_agent} selected for {context.request.insurance_type} insurance guidance.",
            self._theme_rationale(planning_signals["claim_theme"]),
        ]
        if planning_signals["evidence_focus"]:
            rationale.append(f"Planning evidence focus: {', '.join(planning_signals['evidence_focus'])}.")
        if planning_signals.get("model_used"):
            rationale.append("A configured text model classified planning signals before deterministic agent selection.")
        elif planning_signals.get("model_error"):
            rationale.append("Model planning signals were unavailable, so deterministic fallback classification was used.")
        if context.request.damage_image_bytes or context.request.damage_image_filename:
            rationale.append("Damage image was provided, so visual evidence and authenticity agents are required.")
        else:
            rationale.append("No damage image was provided, so vision agents are skipped and evidence completeness is checked instead.")

        skipped_agents = [
            name
            for name in ["VisualEvidenceAgent", "ImageAuthenticityAgent"]
            if name not in planned_agents
        ]
        log_event(
            logger,
            "Planning decision completed.",
            functional_agent=functional_agent,
            planned_agents=", ".join(planned_agents),
            planned_agent_count=len(planned_agents),
            skipped_agents=", ".join(skipped_agents) or "none",
            claim_theme=planning_signals["claim_theme"],
            evidence_focus=", ".join(planning_signals["evidence_focus"]) or "none",
            model_used=planning_signals["model_used"],
            model_name=planning_signals["model_name"],
            model_error=planning_signals["model_error"],
        )
        return self.respond(
            findings=DynamicPlanningFindings(
                planned_agents=planned_agents,
                skipped_agents=skipped_agents,
                rationale=rationale,
                planning_mode="hybrid_model_signals_with_rule_fallback",
                planning_signals=planning_signals,
                tasks=[task.model_dump(mode="json") for task in tasks],
            ),
            confidence=0.94,
            messages=[
                self.message(
                    f"Dynamic execution plan selected {len(planned_agents)} agent(s).",
                    to_agent="OrchestratorAgent",
                    message_type="guidance",
                    metadata={
                        "planned_agents": planned_agents,
                        "task_ids": [task.task_id for task in tasks],
                        "rationale": rationale,
                    },
                )
            ],
        )

    def create_tasks(
        self,
        context: AgentContext,
        planning_signals: PlanningSignalsFindings | None = None,
    ) -> list[InvestigationTask]:
        """Plan only work that can resolve evidence currently absent from state."""
        signals = planning_signals or self._planning_signals(context)
        has_policy = bool(context.request.policy_text.strip())
        has_image = bool(context.request.damage_image_bytes or context.request.damage_image_filename)
        tasks: list[InvestigationTask] = []
        task_ids: dict[InvestigationTaskType, str] = {}

        def add(
            task_type: InvestigationTaskType,
            agent_name: str,
            objective: str,
            reason: str,
            *,
            role: str = "InvestigationPlannerAgent",
            depends_on: list[InvestigationTaskType] | None = None,
            model_calls: int = 0,
        ) -> None:
            resolution_keys = {
                "DomainGuidanceService": [
                    "GeneralInsuranceFunctionalAgent",
                    specialized_functional_agent_name(context.request.insurance_type),
                ],
            }
            keys = resolution_keys.get(agent_name, [agent_name])
            if all(key in context.memory for key in keys):
                return
            task_id = f"task-{len(tasks) + 1:02d}-{task_type.value}"
            dependency_ids = [
                task_ids[item] for item in (depends_on or []) if item in task_ids
            ]
            tasks.append(
                InvestigationTask(
                    task_id=task_id,
                    task_type=task_type,
                    agent_name=agent_name,
                    assigned_role=role,
                    tool_name=None if task_type in {
                        InvestigationTaskType.ANALYZE_COVERAGE,
                        InvestigationTaskType.CRITIQUE_EVIDENCE,
                    } else agent_name,
                    objective=objective,
                    selection_reason=reason,
                    depends_on=dependency_ids,
                    expected_model_calls=model_calls,
                    estimated_cost_usd=0.003 * model_calls,
                )
            )
            task_ids[task_type] = task_id

        add(
            InvestigationTaskType.INGEST_DOCUMENTS,
            "DocumentIngestionAgent",
            "Normalize policy and supporting documents into shared evidence state.",
            "Document state has not yet been ingested.",
        )
        add(
            InvestigationTaskType.EXTRACT_CLAIM,
            "ClaimExtractionAgent",
            "Extract typed claim facts and classify the reported loss.",
            f"Claim facts are unresolved; planning theme is {signals.claim_theme}.",
            model_calls=1,
        )
        if has_policy:
            add(
                InvestigationTaskType.CHECK_DOCUMENT_QUALITY,
                "DocumentQualityAgent",
                "Check whether extracted policy text is usable.",
                "Policy text is present and must be quality-gated before conclusions are trusted.",
                depends_on=[InvestigationTaskType.INGEST_DOCUMENTS],
            )
            add(
                InvestigationTaskType.EXTRACT_POLICY,
                "PolicyConceptExtractionAgent",
                "Extract typed clauses, conditions, dates, limits, and requirements.",
                "Policy concepts are unresolved and policy text is available.",
                depends_on=[InvestigationTaskType.INGEST_DOCUMENTS],
                model_calls=1,
            )
        add(
            InvestigationTaskType.LOAD_DOMAIN_GUIDANCE,
            "DomainGuidanceService",
            "Load general and insurance-domain investigation checks.",
            f"The selected {context.request.insurance_type.value} domain determines required checks.",
            depends_on=[InvestigationTaskType.EXTRACT_CLAIM],
        )
        if has_policy:
            add(
                InvestigationTaskType.REWRITE_QUERY,
                "QueryRewriteAgent",
                "Create a claim- and checklist-specific policy query.",
                "Policy retrieval needs a query grounded in extracted claim facts.",
                depends_on=[
                    InvestigationTaskType.EXTRACT_CLAIM,
                    InvestigationTaskType.EXTRACT_POLICY,
                    InvestigationTaskType.LOAD_DOMAIN_GUIDANCE,
                ],
                model_calls=0,
            )
            add(
                InvestigationTaskType.RETRIEVE_EVIDENCE,
                "RetrievalAgent",
                "Retrieve exact policy and supporting-document passages.",
                "Coverage analysis requires exact passages rather than the whole policy.",
                depends_on=[InvestigationTaskType.REWRITE_QUERY],
            )
        if has_image:
            add(
                InvestigationTaskType.ANALYZE_IMAGE,
                "VisualEvidenceAgent",
                "Extract bounded visual damage observations.",
                "A damage image was supplied and can resolve claim-evidence consistency.",
                model_calls=1,
            )
            add(
                InvestigationTaskType.CHECK_IMAGE_AUTHENTICITY,
                "ImageAuthenticityAgent",
                "Check image integrity risk signals.",
                "A supplied image must be authenticity-screened before it influences the result.",
                model_calls=1,
            )
        add(
            InvestigationTaskType.ANALYZE_COVERAGE,
            "CoverageAnalystAgent",
            "Evaluate coverage and exclusions as explicit propositions.",
            "Claim facts are available and policy evidence must be assessed or declared insufficient.",
            role="CoverageAnalystAgent",
            depends_on=[
                InvestigationTaskType.EXTRACT_CLAIM,
                InvestigationTaskType.RETRIEVE_EVIDENCE,
                InvestigationTaskType.ANALYZE_IMAGE,
                InvestigationTaskType.CHECK_IMAGE_AUTHENTICITY,
            ],
            model_calls=2,
        )
        add(
            InvestigationTaskType.CHECK_DOCUMENTS,
            "MissingDocumentsAgent",
            "Compare supplied evidence with claim and policy requirements.",
            "Evidence completeness is unresolved for every claim.",
            depends_on=[
                InvestigationTaskType.EXTRACT_CLAIM,
                InvestigationTaskType.EXTRACT_POLICY,
                InvestigationTaskType.LOAD_DOMAIN_GUIDANCE,
            ],
        )
        add(
            InvestigationTaskType.CHECK_CONSISTENCY,
            "ConsistencyVerificationAgent",
            "Compare dates, insured subject, claim facts, and visual evidence.",
            "Cross-source consistency and policy-period applicability remain unresolved.",
            depends_on=[
                InvestigationTaskType.EXTRACT_CLAIM,
                InvestigationTaskType.EXTRACT_POLICY,
                InvestigationTaskType.ANALYZE_IMAGE,
            ],
        )
        if self._calculation_supported(context):
            add(
                InvestigationTaskType.CALCULATE_SETTLEMENT,
                "SettlementCalculationService",
                "Compute supported claim amount minus an explicit deductible or excess.",
                "Both a claimed amount and policy deductible/excess are explicitly present.",
            )
        if has_policy:
            add(
                InvestigationTaskType.FORMAT_CITATIONS,
                "CitationAgent",
                "Attach exact retrieved passages to assessment propositions.",
                "Policy propositions require exact provenance before critique.",
                depends_on=[
                    InvestigationTaskType.RETRIEVE_EVIDENCE,
                    InvestigationTaskType.ANALYZE_COVERAGE,
                ],
            )
        add(
            InvestigationTaskType.CRITIQUE_EVIDENCE,
            "EvidenceCriticAgent",
            "Accept or reject propositions and request only targeted repairs.",
            "All available initial evidence has been assembled and must be independently checked.",
            role="EvidenceCriticAgent",
            depends_on=[
                InvestigationTaskType.ANALYZE_COVERAGE,
                InvestigationTaskType.CHECK_DOCUMENTS,
                InvestigationTaskType.CHECK_CONSISTENCY,
                InvestigationTaskType.FORMAT_CITATIONS,
            ],
        )
        return tasks

    @staticmethod
    def _calculation_supported(context: AgentContext) -> bool:
        claim = context.request.claim_description.lower()
        policy = context.request.policy_text.lower()
        return any(char.isdigit() for char in claim) and any(
            term in policy for term in ("deductible", "excess")
        )

    def _legacy_plan(self, tasks: list[InvestigationTask], functional_agent: str) -> list[str]:
        names: list[str] = []
        for task in tasks:
            if task.task_type is InvestigationTaskType.LOAD_DOMAIN_GUIDANCE:
                names.extend(["GeneralInsuranceFunctionalAgent", functional_agent])
            elif task.task_type is InvestigationTaskType.ANALYZE_COVERAGE:
                names.extend(["CoverageMatchingAgent", "ExclusionCheckingAgent"])
            elif task.task_type is InvestigationTaskType.CRITIQUE_EVIDENCE:
                names.extend(["OutputValidatorAgent", "FinalDecisionSynthesisAgent"])
            elif task.agent_name not in {"SettlementCalculationService"}:
                names.append(task.agent_name)
        return list(dict.fromkeys(names))

    def _planning_signals(self, context: AgentContext) -> PlanningSignalsFindings:
        fallback = self._fallback_planning_signals(context.request.claim_description)
        model_client = get_model_client()
        log_event(
            logger,
            "Planning signal classification started.",
            model_name=model_client.planning_model,
            fallback_theme=fallback["claim_theme"],
            fallback_evidence_focus=", ".join(fallback["evidence_focus"]) or "none",
        )
        model_result = model_client.json_response(
            system=(
                "You classify insurance claim planning signals. Return only valid JSON. "
                "Do not return or invent agent names. The application will choose agents deterministically."
            ),
            prompt=(
                "Classify the claim for planning. Use this exact JSON shape: "
                "{claim_theme, evidence_focus, rationale}. "
                f"claim_theme must be one of: {self._allowed_theme_prompt()}. "
                "evidence_focus must be a short array of evidence types to emphasize.\n\n"
                f"INSURANCE TYPE: {context.request.insurance_type}\n"
                f"CLAIM DESCRIPTION:\n{context.request.claim_description}"
            ),
            fallback=fallback,
            model=model_client.planning_model,
            schema_name="planning_signals",
            response_model=PlanningSignalsModelOutput,
            schema_description="Planning signals used to explain deterministic insurance agent selection.",
        )
        data = model_result.data
        theme = self._valid_theme(data.get("claim_theme"))
        evidence_focus = self._text_list(data.get("evidence_focus"))[:5]
        rationale = str(data.get("rationale", fallback["rationale"]))
        log_event(
            logger,
            "Planning signal classification completed.",
            claim_theme=theme,
            evidence_focus=", ".join(evidence_focus) or "none",
            model_used=model_result.used_model,
            model_name=model_client.planning_model,
            model_error=model_result.error,
        )
        return PlanningSignalsFindings(
            claim_theme=theme,
            evidence_focus=evidence_focus,
            rationale=rationale,
            model_used=model_result.used_model,
            model_name=model_client.planning_model,
            model_error=model_result.error,
        )

    def _fallback_planning_signals(self, claim_description: str) -> dict[str, Any]:
        lower_claim = claim_description.lower()
        for theme, config in CLAIM_THEME_CONFIG.items():
            if self._has_any(lower_claim, *config["keywords"]):
                return {
                    "claim_theme": theme,
                    "evidence_focus": config["evidence_focus"],
                    "rationale": config["fallback_rationale"],
                }
        return {
            "claim_theme": UNKNOWN_THEME,
            "evidence_focus": [],
            "rationale": UNKNOWN_THEME_RATIONALE,
        }

    def _valid_theme(self, value: object) -> str:
        theme = str(value or UNKNOWN_THEME).strip().lower()
        return theme if theme in self._allowed_themes() else UNKNOWN_THEME

    @classmethod
    def _theme_rationale(cls, theme: str) -> str:
        config = CLAIM_THEME_CONFIG.get(theme)
        if config:
            return config["theme_rationale"]
        return UNKNOWN_THEME_RATIONALE

    @classmethod
    def _allowed_theme_prompt(cls) -> str:
        return ", ".join(cls._allowed_themes())

    @classmethod
    def _allowed_themes(cls) -> list[str]:
        return [*CLAIM_THEME_CONFIG.keys(), UNKNOWN_THEME]

    @staticmethod
    def _text_list(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if value:
            return [str(value)]
        return []

    @staticmethod
    def _has_any(text: str, *terms: str) -> bool:
        return any(term in text for term in terms)


# Import compatibility for Phase 1-4 callers. The implementation is the Phase 5 role.
DynamicPlanningAgent = InvestigationPlannerAgent


__all__ = ["DynamicPlanningAgent", "InvestigationPlannerAgent"]

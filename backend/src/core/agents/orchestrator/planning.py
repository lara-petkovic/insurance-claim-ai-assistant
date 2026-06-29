from __future__ import annotations

from typing import Any

from core.agents.base import AgentContext, BaseAgent
from core.agents.constants import CLAIM_THEME_CONFIG, UNKNOWN_THEME, UNKNOWN_THEME_RATIONALE
from core.agents.technical_agents.shared import specialized_functional_agent_name
from core.models.agent import AgentResponse
from models.model_client import get_model_client
from utils.app_logger import get_logger, log_event

logger = get_logger("agents.DynamicPlanningAgent")


class DynamicPlanningAgent(BaseAgent):
    """Selects the execution plan and specialized functional agent for each claim."""

    name = "DynamicPlanningAgent"
    agent_type = "orchestrator"

    BASE_PLAN_BEFORE_FUNCTIONAL = [
        "DocumentIngestionAgent",
        "DocumentQualityAgent",
        "PolicyConceptExtractionAgent",
        "ClaimExtractionAgent",
        "GeneralInsuranceFunctionalAgent",
    ]
    BASE_PLAN_AFTER_FUNCTIONAL = [
        "QueryRewriteAgent",
        "RetrievalAgent",
        "CoverageMatchingAgent",
        "ExclusionCheckingAgent",
        "MissingDocumentsAgent",
        "ConsistencyVerificationAgent",
        "CitationAgent",
        "OutputValidatorAgent",
        "FinalDecisionSynthesisAgent",
    ]

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
        planned_agents = [
            *self.BASE_PLAN_BEFORE_FUNCTIONAL,
            functional_agent,
            *self.BASE_PLAN_AFTER_FUNCTIONAL,
        ]
        rationale = [
            "Always ingest the policy, extract policy concepts, classify the claim, retrieve evidence, validate, and synthesize.",
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
            insertion_index = planned_agents.index("CoverageMatchingAgent")
            planned_agents[insertion_index:insertion_index] = ["VisualEvidenceAgent", "ImageAuthenticityAgent"]
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
            findings={
                "planned_agents": planned_agents,
                "skipped_agents": skipped_agents,
                "rationale": rationale,
                "planning_mode": "hybrid_model_signals_with_rule_fallback",
                "planning_signals": planning_signals,
            },
            confidence=0.94,
            messages=[
                self.message(
                    f"Dynamic execution plan selected {len(planned_agents)} agent(s).",
                    to_agent="OrchestratorAgent",
                    message_type="guidance",
                    metadata={"planned_agents": planned_agents, "rationale": rationale},
                )
            ],
        )

    def _planning_signals(self, context: AgentContext) -> dict[str, Any]:
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
        return {
            "claim_theme": theme,
            "evidence_focus": evidence_focus,
            "rationale": rationale,
            "model_used": model_result.used_model,
            "model_name": model_client.planning_model,
            "model_error": model_result.error,
        }

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

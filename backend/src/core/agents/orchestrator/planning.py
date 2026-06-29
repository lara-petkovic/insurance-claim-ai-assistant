from __future__ import annotations

from core.agents.base import AgentContext, BaseAgent
from core.agents.technical_agents.shared import specialized_functional_agent_name
from core.models.agent import AgentResponse


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
        functional_agent = specialized_functional_agent_name(context.request.insurance_type)
        planned_agents = [
            *self.BASE_PLAN_BEFORE_FUNCTIONAL,
            functional_agent,
            *self.BASE_PLAN_AFTER_FUNCTIONAL,
        ]
        rationale = [
            "Always ingest the policy, extract policy concepts, classify the claim, retrieve evidence, validate, and synthesize.",
            f"{functional_agent} selected for {context.request.insurance_type} insurance guidance.",
        ]
        lower_claim = context.request.claim_description.lower()
        if any(term in lower_claim for term in ["stolen", "theft", "burglar", "broke into"]):
            rationale.append("The claim text suggests theft, so evidence planning emphasizes police report and ownership checks.")
        elif any(term in lower_claim for term in ["storm", "roof", "hail", "wind"]):
            rationale.append("The claim text suggests storm damage, so planning emphasizes weather evidence and wear-and-tear exclusions.")
        elif any(term in lower_claim for term in ["leak", "water", "pipe", "ceiling", "flood"]):
            rationale.append("The claim text suggests water damage, so planning emphasizes sudden escape of water, gradual damage exclusions, and plumber evidence.")
        else:
            rationale.append("The claim type is not obvious from text, so the complete validation path is kept.")
        if context.request.damage_image_bytes or context.request.damage_image_filename:
            insertion_index = planned_agents.index("CoverageMatchingAgent")
            planned_agents[insertion_index:insertion_index] = ["VisualEvidenceAgent", "ImageAuthenticityAgent"]
            rationale.append("Damage image was provided, so visual evidence and authenticity agents are required.")
        else:
            rationale.append("No damage image was provided, so vision agents are skipped and evidence completeness is checked instead.")

        return self.respond(
            findings={
                "planned_agents": planned_agents,
                "skipped_agents": [
                    name
                    for name in ["VisualEvidenceAgent", "ImageAuthenticityAgent"]
                    if name not in planned_agents
                ],
                "rationale": rationale,
                "planning_mode": "dynamic_rule_based",
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

from __future__ import annotations

from app.agents.base import AgentContext, BaseAgent
from app.schemas.agent import AgentResponse

class GeneralInsuranceFunctionalAgent(BaseAgent):
    name = "GeneralInsuranceFunctionalAgent"
    agent_type = "functional"

    def run(self, context: AgentContext) -> AgentResponse:
        rules = [
            "event_must_occur_during_active_policy_period",
            "insured_object_or_person_must_match_claim",
            "exclusions_must_be_checked_before_coverage_recommendation",
            "required_evidence_must_be_present",
            "uncertainty_should_trigger_human_review",
        ]
        checklist = [
            {"check": "policy_period", "instruction": "Verify the incident date can be evaluated against the policy period."},
            {"check": "insured_subject", "instruction": "Confirm the damaged object/person matches the insured subject."},
            {"check": "coverage_before_exclusions", "instruction": "Match coverage first, then check exclusions before recommendation."},
            {"check": "evidence_completeness", "instruction": "Flag missing evidence instead of forcing a final decision."},
            {"check": "human_review", "instruction": "Send uncertain, inconsistent, or unsupported outcomes to human review."},
        ]
        instructions = [
            {"target_agent": "CoverageMatchingAgent", "instruction": "Use policy evidence conservatively and do not mark covered without support."},
            {"target_agent": "ExclusionCheckingAgent", "instruction": "Check exclusions after coverage matching and flag uncertainty for human review."},
            {"target_agent": "MissingDocumentsAgent", "instruction": "Treat missing evidence as a human-review reason, not as automatic denial."},
            {"target_agent": "OutputValidatorAgent", "instruction": "Reject unsupported final decisions and preserve review reasons."},
        ]
        return self.respond(
            findings={"rules": rules, "checklist": checklist, "instructions": instructions},
            confidence=0.95,
            messages=[
                self.message(
                    "Functional checklist prepared for all technical agents: validate policy period, coverage, exclusions, evidence, and uncertainty.",
                    to_agent="OrchestratorAgent",
                    message_type="guidance",
                    metadata={"checks": [item["check"] for item in checklist], "instructions": instructions},
                )
            ],
        )


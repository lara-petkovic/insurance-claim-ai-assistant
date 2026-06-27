from __future__ import annotations

from core.agents.base import AgentContext, BaseAgent
from core.models.agent import AgentResponse


class TravelInsuranceFunctionalAgent(BaseAgent):
    """Acts as a travel-insurance domain expert and defines travel-claim checks."""

    name = "TravelInsuranceFunctionalAgent"
    agent_type = "functional"

    def run(self, context: AgentContext) -> AgentResponse:
        claim_type = context.memory.get("ClaimExtractionAgent", {}).get("claim_type", "unknown")
        rules_by_claim_type = {
            "baggage_loss": [
                "baggage_loss_may_be_covered_when loss_theft_or_damage_occurs_during_the_trip",
                "unattended_baggage_or_missing_carrier_report_may_limit_cover",
                "proof_of_ownership_and_carrier_or_police_report_are_often_required",
            ],
            "medical": [
                "emergency_medical_expenses_may_be_covered_for_sudden_illness_or_accident_abroad",
                "pre_existing_conditions_or_non_emergency_treatment_may_be_excluded",
                "medical_report_and_receipts_are_expected",
            ],
            "trip_cancellation": [
                "trip_cancellation_requires_a_covered_reason_before_departure",
                "known_events_or_change_of_mind_are_commonly_excluded",
                "booking_confirmation_and_cancellation_evidence_are_required",
            ],
        }
        selected_rules = rules_by_claim_type.get(claim_type, [])
        checklist_by_claim_type = {
            "baggage_loss": [
                {"check": "loss_theft_or_damage_during_trip", "target_agent": "CoverageMatchingAgent"},
                {"check": "unattended_baggage", "target_agent": "ExclusionCheckingAgent"},
                {"check": "carrier_or_police_report", "target_agent": "MissingDocumentsAgent"},
                {"check": "proof_of_ownership", "target_agent": "MissingDocumentsAgent"},
            ],
            "medical": [
                {"check": "emergency_medical_event", "target_agent": "CoverageMatchingAgent"},
                {"check": "pre_existing_condition", "target_agent": "ExclusionCheckingAgent"},
                {"check": "medical_report", "target_agent": "MissingDocumentsAgent"},
                {"check": "medical_receipts", "target_agent": "MissingDocumentsAgent"},
            ],
            "trip_cancellation": [
                {"check": "covered_cancellation_reason", "target_agent": "CoverageMatchingAgent"},
                {"check": "known_event_or_change_of_mind", "target_agent": "ExclusionCheckingAgent"},
                {"check": "booking_confirmation", "target_agent": "MissingDocumentsAgent"},
                {"check": "cancellation_evidence", "target_agent": "MissingDocumentsAgent"},
            ],
        }
        selected_checklist = checklist_by_claim_type.get(claim_type, [])
        instructions = [
            {
                "target_agent": item["target_agent"],
                "instruction": f"For travel {claim_type}, perform functional check: {item['check']}.",
                "priority": "high",
            }
            for item in selected_checklist
        ]
        return self.respond(
            findings={
                "rules_by_claim_type": rules_by_claim_type,
                "selected_claim_type": claim_type,
                "selected_rules": selected_rules,
                "checklist": selected_checklist,
                "instructions": instructions,
            },
            confidence=0.9 if selected_checklist else 0.55,
            requires_human_review=not bool(selected_checklist),
            messages=[
                self.message(
                    f"Travel insurance guidance prepared for {claim_type}: {len(selected_checklist)} targeted checks.",
                    to_agent="OrchestratorAgent",
                    message_type="guidance",
                    metadata={"claim_type": claim_type, "checks": selected_checklist, "instructions": instructions},
                )
            ],
        )

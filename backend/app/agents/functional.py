from __future__ import annotations

from app.agents.base import AgentContext, BaseAgent
from app.schemas.agent import AgentResponse


class GeneralInsuranceFunctionalAgent(BaseAgent):
    name = "GeneralInsuranceFunctionalAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        rules = [
            "event_must_occur_during_active_policy_period",
            "insured_object_or_person_must_match_claim",
            "exclusions_must_be_checked_before_coverage_recommendation",
            "required_evidence_must_be_present",
            "uncertainty_should_trigger_human_review",
        ]
        return AgentResponse(
            agent_name=self.name,
            findings={"rules": rules},
            confidence=0.95,
        )


class HomeInsuranceFunctionalAgent(BaseAgent):
    name = "HomeInsuranceFunctionalAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        rules_by_claim_type = {
            "water_damage": [
                "water_damage_may_be_covered_when_caused_by_sudden_escape_of_water",
                "gradual_leakage_rot_or_poor_maintenance_may_be_excluded",
                "damage_to_the_pipe_or_apparatus_itself_may_be_excluded",
                "plumber_report_or_cause_confirmation_is_often_required",
            ],
            "storm_damage": [
                "storm_or_flood_coverage_must_be_separated_from_wear_and_tear",
                "weather_evidence_may_be_required",
                "pre_existing_roof_damage_or_poor_maintenance_may_be_excluded",
            ],
            "theft": [
                "theft_usually_requires_police_report",
                "forcible_or_violent_entry_may_be_required",
                "proof_of_ownership_may_be_required_for_stolen_items",
            ],
            "fire_damage": [
                "fire_damage_requires_incident_evidence",
                "smoke_damage_arising_gradually_may_be_excluded",
            ],
            "broken_glass": [
                "broken_glass_may_be_separately_covered",
                "damage_photos_and_repair_estimate_are_expected",
            ],
        }
        return AgentResponse(
            agent_name=self.name,
            findings={"rules_by_claim_type": rules_by_claim_type},
            confidence=0.92,
        )


from __future__ import annotations

from core.agents.base import AgentContext, BaseAgent
from core.models.agent import AgentResponse


class HomeInsuranceFunctionalAgent(BaseAgent):
    name = "HomeInsuranceFunctionalAgent"
    agent_type = "functional"

    def run(self, context: AgentContext) -> AgentResponse:
        claim_type = context.memory.get("ClaimExtractionAgent", {}).get("claim_type", "unknown")
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
        selected_rules = rules_by_claim_type.get(claim_type, [])
        checklist_by_claim_type = {
            "water_damage": [
                {"check": "sudden_escape_of_water", "target_agent": "CoverageMatchingAgent"},
                {"check": "gradual_leakage_or_rot", "target_agent": "ExclusionCheckingAgent"},
                {"check": "pipe_or_apparatus_itself", "target_agent": "ExclusionCheckingAgent"},
                {"check": "plumber_report", "target_agent": "MissingDocumentsAgent"},
                {"check": "repair_estimate", "target_agent": "MissingDocumentsAgent"},
            ],
            "storm_damage": [
                {"check": "weather_event", "target_agent": "CoverageMatchingAgent"},
                {"check": "wear_and_tear", "target_agent": "ExclusionCheckingAgent"},
                {"check": "weather_report", "target_agent": "MissingDocumentsAgent"},
            ],
            "theft": [
                {"check": "forcible_entry", "target_agent": "CoverageMatchingAgent"},
                {"check": "police_report", "target_agent": "MissingDocumentsAgent"},
                {"check": "proof_of_ownership", "target_agent": "MissingDocumentsAgent"},
            ],
        }
        selected_checklist = checklist_by_claim_type.get(claim_type, [])
        instructions = [
            {
                "target_agent": item["target_agent"],
                "instruction": f"For {claim_type}, perform functional check: {item['check']}.",
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
            confidence=0.92,
            messages=[
                self.message(
                    f"Home insurance guidance prepared for {claim_type}: {len(selected_checklist)} targeted checks.",
                    to_agent="OrchestratorAgent",
                    message_type="guidance",
                    metadata={"claim_type": claim_type, "checks": selected_checklist, "instructions": instructions},
                )
            ],
        )

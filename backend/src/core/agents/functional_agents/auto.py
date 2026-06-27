from __future__ import annotations

from core.agents.base import AgentContext, BaseAgent
from core.models.agent import AgentResponse


class AutoInsuranceFunctionalAgent(BaseAgent):
    """Acts as an auto-insurance domain expert and defines vehicle-claim checks."""

    name = "AutoInsuranceFunctionalAgent"
    agent_type = "functional"

    def run(self, context: AgentContext) -> AgentResponse:
        claim_type = context.memory.get("ClaimExtractionAgent", {}).get("claim_type", "unknown")
        rules_by_claim_type = {
            "vehicle_damage": [
                "vehicle_damage_may_be_covered_when_collision_or_accidental_damage_cover_applies",
                "wear_and_tear_mechanical_breakdown_or_unapproved_repairs_may_be_excluded",
                "repair_estimate_and_damage_photos_are_expected",
                "police_report_or_third_party_details_may_be_required_for_accidents_theft_or_liability",
            ],
            "theft": [
                "vehicle_theft_usually_requires_police_report",
                "keys_security_and_forcible_entry_conditions_may_apply",
                "proof_of_ownership_and_vehicle_registration_may_be_required",
            ],
            "fire_damage": [
                "vehicle_fire_damage_requires_incident_evidence",
                "intentional_damage_or_poor_maintenance_may_be_excluded",
            ],
        }
        selected_rules = rules_by_claim_type.get(claim_type, [])
        checklist_by_claim_type = {
            "vehicle_damage": [
                {"check": "collision_or_accidental_damage_cover", "target_agent": "CoverageMatchingAgent"},
                {"check": "wear_and_tear_or_mechanical_breakdown", "target_agent": "ExclusionCheckingAgent"},
                {"check": "repair_estimate", "target_agent": "MissingDocumentsAgent"},
                {"check": "damage_photos", "target_agent": "MissingDocumentsAgent"},
            ],
            "theft": [
                {"check": "vehicle_theft_cover", "target_agent": "CoverageMatchingAgent"},
                {"check": "security_conditions", "target_agent": "ExclusionCheckingAgent"},
                {"check": "police_report", "target_agent": "MissingDocumentsAgent"},
                {"check": "vehicle_registration", "target_agent": "MissingDocumentsAgent"},
            ],
            "fire_damage": [
                {"check": "fire_cover", "target_agent": "CoverageMatchingAgent"},
                {"check": "incident_report", "target_agent": "MissingDocumentsAgent"},
                {"check": "repair_estimate", "target_agent": "MissingDocumentsAgent"},
            ],
        }
        selected_checklist = checklist_by_claim_type.get(claim_type, [])
        instructions = [
            {
                "target_agent": item["target_agent"],
                "instruction": f"For auto {claim_type}, perform functional check: {item['check']}.",
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
                    f"Auto insurance guidance prepared for {claim_type}: {len(selected_checklist)} targeted checks.",
                    to_agent="OrchestratorAgent",
                    message_type="guidance",
                    metadata={"claim_type": claim_type, "checks": selected_checklist, "instructions": instructions},
                )
            ],
        )

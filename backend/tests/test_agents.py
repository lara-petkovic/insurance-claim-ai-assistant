from app.agents.orchestrator import OrchestratorAgent
from app.schemas.claim import ClaimRequestData


TEST_POLICY_TEXT = """
Household policy wording.
What is covered: escape of water from a fixed water installation, storm, flood,
fire, theft, and accidental breakage of fixed glass.
What is not covered: gradual leakage, rot, poor maintenance, and damage to the
pipe or apparatus from which water escaped.
Claims require damage photos, plumber report and repair estimate for water
damage. Theft requires police report and proof of ownership.
"""


def test_orchestrator_returns_human_review_for_incomplete_water_claim():
    result = OrchestratorAgent().analyze(
        ClaimRequestData(
            insurance_type="home",
            claim_description="A pipe burst in my bathroom and caused water damage to the ceiling and floor.",
            incident_date="2026-03-12",
            policy_text=TEST_POLICY_TEXT,
            damage_image_filename="water_damage_ceiling.jpg",
        )
    )

    assert result.claim_type == "water_damage"
    assert result.coverage_assessment == "covered"
    assert result.claim_status == "requires_human_review"
    assert "plumber report" in result.missing_documents
    assert result.evidence


def test_orchestrator_flags_gradual_damage_exclusion():
    result = OrchestratorAgent().analyze(
        ClaimRequestData(
            insurance_type="home",
            claim_description="A slow leak over many months caused rot and mold in the wall.",
            incident_date="2026-03-12",
            policy_text=TEST_POLICY_TEXT,
            damage_image_filename="water_damage_wall.jpg",
        )
    )

    assert result.claim_status == "likely_not_covered"
    assert any(item["concept"] in {"gradual_damage", "rot"} for item in result.potential_exclusions)

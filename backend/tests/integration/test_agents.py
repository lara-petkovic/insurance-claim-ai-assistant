from config import get_settings
from core.agents.orchestrator import OrchestratorAgent
from core.models.claim import ClaimRequestData
from models.model_client import get_model_client

TEST_POLICY_TEXT = """
Household policy wording.
What is covered: escape of water from a fixed water installation, storm, flood,
fire, theft, and accidental breakage of fixed glass.
What is not covered: gradual leakage, rot, poor maintenance, and damage to the
pipe or apparatus from which water escaped.
Claims require damage photos, plumber report and repair estimate for water
damage. Theft requires police report and proof of ownership.
"""


def disable_model_calls(monkeypatch):
    monkeypatch.setenv("OPENAI_REQUIRE_MODELS", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_FILE", raising=False)
    get_settings.cache_clear()
    get_model_client.cache_clear()


def test_orchestrator_returns_human_review_for_incomplete_water_claim(monkeypatch):
    disable_model_calls(monkeypatch)

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
    assert any(agent.agent_name == "FinalDecisionSynthesisAgent" for agent in result.agent_trace)
    assert any(message.to_agent for agent in result.agent_trace for message in agent.messages)
    assert any(agent.agent_name == "DocumentQualityAgent" for agent in result.agent_trace)
    assert any(agent.agent_name == "QueryRewriteAgent" for agent in result.agent_trace)


def test_orchestrator_flags_gradual_damage_exclusion(monkeypatch):
    disable_model_calls(monkeypatch)

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
    validator = next(agent for agent in result.agent_trace if agent.agent_name == "OutputValidatorAgent")
    assert validator.findings["feedback"]


def test_orchestrator_dynamic_plan_skips_vision_agents_without_image(monkeypatch):
    disable_model_calls(monkeypatch)

    result = OrchestratorAgent().analyze(
        ClaimRequestData(
            insurance_type="home",
            claim_description="A pipe burst in my bathroom and caused water damage to the ceiling.",
            incident_date="2026-03-12",
            policy_text=TEST_POLICY_TEXT,
        )
    )

    trace_names = [agent.agent_name for agent in result.agent_trace]
    planner = next(agent for agent in result.agent_trace if agent.agent_name == "DynamicPlanningAgent")

    assert "VisualEvidenceAgent" not in trace_names
    assert "ImageAuthenticityAgent" not in trace_names
    assert "VisualEvidenceAgent" in planner.findings["skipped_agents"]
    assert any("water damage" in reason for reason in planner.findings["rationale"])
    assert "FinalDecisionSynthesisAgent" in trace_names

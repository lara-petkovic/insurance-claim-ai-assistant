from config import get_settings
from core.agents.base import AgentContext
from core.agents.orchestrator.planning import DynamicPlanningAgent
from core.agents.orchestrator import OrchestratorAgent
from core.models.claim import ClaimRequestData
from models.model_client import ModelResult, get_model_client

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
    monkeypatch.delenv("OPENAI_PLANNING_MODEL", raising=False)
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


def test_dynamic_planner_uses_model_signals_without_model_generated_agent_list(monkeypatch):
    class FakeModelClient:
        planning_model = "planner-test-model"

        def json_response(self, **kwargs):
            assert kwargs["model"] == self.planning_model
            return ModelResult(
                data={
                    "claim_theme": "theft",
                    "evidence_focus": ["police report", "ownership proof"],
                    "rationale": "The user says valuable items disappeared from the home.",
                    "planned_agents": ["UntrustedAgent"],
                },
                used_model=True,
            )

    monkeypatch.setattr("core.agents.orchestrator.planning.get_model_client", lambda: FakeModelClient())
    response = DynamicPlanningAgent().run(
        AgentContext(
            request=ClaimRequestData(
                insurance_type="home",
                claim_description="My watch disappeared after someone entered the house.",
                policy_text=TEST_POLICY_TEXT,
            )
        )
    )

    assert response.findings["planning_signals"]["claim_theme"] == "theft"
    assert response.findings["planning_signals"]["model_used"] is True
    assert response.findings["planning_signals"]["model_name"] == "planner-test-model"
    assert "UntrustedAgent" not in response.findings["planned_agents"]
    assert "HomeInsuranceFunctionalAgent" in response.findings["planned_agents"]


def test_orchestrator_uses_auto_functional_agent_for_auto_claim(monkeypatch):
    disable_model_calls(monkeypatch)

    result = OrchestratorAgent().analyze(
        ClaimRequestData(
            insurance_type="auto",
            claim_description="My car was in a collision and the bumper needs repair.",
            incident_date="2026-03-12",
            policy_text="Comprehensive vehicle cover includes collision and accidental damage. Claims require damage photos and repair estimate.",
            damage_image_filename="vehicle_damage.jpg",
        )
    )

    trace_names = [agent.agent_name for agent in result.agent_trace]

    assert result.claim_type == "vehicle_damage"
    assert "AutoInsuranceFunctionalAgent" in trace_names
    assert "HomeInsuranceFunctionalAgent" not in trace_names


def test_orchestrator_uses_travel_functional_agent_for_travel_claim(monkeypatch):
    disable_model_calls(monkeypatch)

    result = OrchestratorAgent().analyze(
        ClaimRequestData(
            insurance_type="travel",
            claim_description="The airline lost my luggage during the trip.",
            incident_date="2026-03-12",
            policy_text="Travel policy covers baggage and lost luggage. Claims require carrier report and proof of ownership.",
        )
    )

    trace_names = [agent.agent_name for agent in result.agent_trace]

    assert result.claim_type == "baggage_loss"
    assert "TravelInsuranceFunctionalAgent" in trace_names
    assert "HomeInsuranceFunctionalAgent" not in trace_names

from config import get_settings
from core.agents.orchestrator import OrchestratorAgent
from core.agents.technical_agents.output_validator import OutputValidatorAgent
from core.models.analysis import OrchestrationLimits
from core.models.claim import ClaimRequestData
from models.model_client import ModelClient, ModelResult, get_model_client


POLICY = (
    "Home policy. Covered events include escape of water from a fixed installation. "
    "The policy period is 01/01/2026 to 31/12/2026. "
    "Claims require a plumber report and repair estimate."
)


def disable_model_calls(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_FILE", raising=False)
    get_settings.cache_clear()
    get_model_client.cache_clear()
    monkeypatch.setattr(
        ModelClient,
        "_fallback_or_raise",
        lambda self, fallback, error: ModelResult(data=fallback, used_model=False, error=error),
    )


def request(*, policy_text=POLICY, image=False):
    return ClaimRequestData(
        insurance_type="home",
        claim_description="A burst pipe caused water damage in my bathroom.",
        incident_date="2026-03-12",
        policy_text=policy_text,
        damage_image_filename="damage.jpg" if image else None,
    )


def test_planner_branch_controls_tools_that_actually_run(monkeypatch):
    disable_model_calls(monkeypatch)
    orchestrator = OrchestratorAgent()

    orchestrator.analyze(request(policy_text="", image=False))
    state = orchestrator.last_run_state

    assert state is not None
    task_types = {task.task_type.value for task in state.tasks}
    action_types = {action.task_type.value for action in state.actions}
    assert "extract_policy" not in task_types
    assert "retrieve_evidence" not in task_types
    assert "analyze_image" not in task_types
    assert "extract_claim" in action_types
    assert all(action.reason for action in state.actions)
    follow_up = orchestrator.planner.create_tasks(
        state,
        planning_signals=state.memory["InvestigationPlannerAgent"]["planning_signals"],
    )
    assert follow_up == []

    orchestrator.analyze(request(image=True))
    state = orchestrator.last_run_state
    assert state is not None
    completed = {action.task_type.value for action in state.actions if action.outcome == "completed"}
    assert {"extract_policy", "retrieve_evidence", "analyze_image"} <= completed


def test_critic_requests_and_executes_targeted_repair(monkeypatch):
    disable_model_calls(monkeypatch)
    validation_calls = 0

    def controlled_validation(self, context):
        nonlocal validation_calls
        validation_calls += 1
        validations = {
            item.proposition_id: {
                "valid": validation_calls > 1,
                "issues": [] if validation_calls > 1 else ["no exact cited passage corresponds"],
                "cited_policy_clause_ids": [],
            }
            for item in context.propositions
        }
        first_id = next(iter(validations), "coverage-water_damage")
        feedback = [] if validation_calls > 1 else [
            {
                "target_agent": "CoverageMatchingAgent",
                "issue": f"Proposition {first_id} is not grounded: no exact cited passage corresponds.",
                "suggested_action": "Retrieve the exact passage.",
            }
        ]
        return self.respond(
            findings={
                "feedback": feedback,
                "proposition_validation": validations,
                "coverage_gate_passed": validation_calls > 1,
                "validated_coverage_assessment": "covered",
            },
            confidence=1.0,
            requires_human_review=bool(feedback),
        )

    monkeypatch.setattr(OutputValidatorAgent, "run", controlled_validation)
    orchestrator = OrchestratorAgent()

    orchestrator.analyze(request())
    state = orchestrator.last_run_state

    assert state is not None
    assert state.stop_reason == "sufficient_evidence"
    assert state.usage.repair_iterations == 1
    targeted = next(task for task in state.tasks if task.task_id == "repair-1-retrieve")
    assert targeted.parameters["proposition_ids"]
    assert targeted.parameters["query"]
    assert targeted.status == "completed"
    assert any(action.task_id == "repair-1-reanalyze" for action in state.actions)


def test_repair_iteration_limit_stops_graph(monkeypatch):
    disable_model_calls(monkeypatch)

    def always_reject(self, context):
        validations = {
            item.proposition_id: {
                "valid": False,
                "issues": ["no exact cited passage corresponds"],
                "cited_policy_clause_ids": [],
            }
            for item in context.propositions
        }
        first_id = next(iter(validations), "coverage-water_damage")
        return self.respond(
            findings={
                "feedback": [
                    {
                        "target_agent": "CoverageMatchingAgent",
                        "issue": f"Proposition {first_id} is not grounded: no exact cited passage corresponds.",
                        "suggested_action": "Retrieve exact evidence.",
                    }
                ],
                "proposition_validation": validations,
                "coverage_gate_passed": False,
                "validated_coverage_assessment": "unclear",
            },
            requires_human_review=True,
        )

    monkeypatch.setattr(OutputValidatorAgent, "run", always_reject)
    orchestrator = OrchestratorAgent(
        limits=OrchestrationLimits(max_repair_iterations=1, max_model_calls=20)
    )

    orchestrator.analyze(request())
    state = orchestrator.last_run_state

    assert state is not None
    assert state.stop_reason == "budget_exhausted"
    assert state.usage.repair_iterations == 1
    assert "Maximum repair iterations" in state.stop_detail
    assert not any(task.task_id.startswith("repair-2-") for task in state.tasks)


def test_model_call_limit_and_unresolved_evidence_have_explicit_stops(monkeypatch):
    disable_model_calls(monkeypatch)
    limited = OrchestratorAgent(
        limits=OrchestrationLimits(max_model_calls=1, max_repair_iterations=0)
    )
    limited.analyze(request())
    limited_state = limited.last_run_state

    assert limited_state is not None
    assert limited_state.stop_reason == "budget_exhausted"
    assert limited_state.usage.model_calls == 1
    assert "maximum model calls" in limited_state.stop_detail

    unresolved = OrchestratorAgent()
    result = unresolved.analyze(request(policy_text=""))
    unresolved_state = unresolved.last_run_state

    assert unresolved_state is not None
    assert unresolved_state.stop_reason == "unavoidable_uncertainty"
    assert result.claim_status == "requires_human_review"
    assert "unavoidable_uncertainty" in result.reasoning_summary


def test_stream_adapter_preserves_existing_event_contract(monkeypatch):
    disable_model_calls(monkeypatch)
    events = list(OrchestratorAgent().stream(request(policy_text="")))

    assert events[0]["event"] == "analysis_started"
    assert events[-1]["event"] == "analysis_completed"
    assert {item["event"] for item in events} <= {
        "analysis_started",
        "agent_started",
        "agent_completed",
        "analysis_completed",
        "analysis_failed",
    }
    assert events[-1]["result"]["orchestration"]["stop_reason"] == "unavoidable_uncertainty"

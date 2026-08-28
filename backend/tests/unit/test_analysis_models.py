import pytest
from pydantic import ValidationError

from core.models.agent import AgentResponse
from core.models.analysis import (
    ClaimFact,
    ImageIntegrityModelOutput,
    InvestigationTask,
    OrchestrationLimits,
    PolicyClause,
    PolicyDocument,
    VisualEvidenceModelOutput,
)
from core.models.claim import ClaimRequestData
from core.models.run_state import ClaimAnalysisRunState


def _provenance() -> dict:
    return {
        "source_document_id": "doc-policy-1",
        "source_filename": "policy.pdf",
        "page": 2,
        "section_heading": "COVERED EVENTS",
        "evidence_text": "Escape of water is covered.",
        "char_start": 25,
        "char_end": 52,
        "stable_location": "page:2:chars:25-52",
        "extraction_method": "pdf_text_extraction",
        "confidence": 0.9,
        "verification_status": "machine_verified",
    }


def test_policy_clause_and_claim_fact_require_valid_provenance():
    clause = PolicyClause(
        **_provenance(),
        clause_id="clause-1",
        concept="water_damage",
        clause_type="coverage",
        polarity="covered",
    )
    fact = ClaimFact(
        **{**_provenance(), "source_document_id": "claim-description", "source_filename": "claim_description"},
        fact_id="fact-1",
        fact_type="claimed_cause",
        value="burst pipe",
    )

    assert clause.page == 2
    assert clause.evidence_text == "Escape of water is covered."
    assert fact.verification_status == "machine_verified"


@pytest.mark.parametrize(
    "model, payload",
    [
        (VisualEvidenceModelOutput, {"detected_damage": "water_damage", "confidence": 1.01, "notes": []}),
        (ImageIntegrityModelOutput, {"risk_level": "high", "risk_score": -0.01, "signals": []}),
        (AgentResponse, {"agent_name": "agent", "confidence": 2}),
    ],
)
def test_confidence_and_risk_scores_are_bounded(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_exact_evidence_offsets_must_match_text_length():
    with pytest.raises(ValidationError, match="span the exact evidence text"):
        PolicyClause(
            **{**_provenance(), "char_end": 51},
            clause_id="clause-1",
            concept="water_damage",
            clause_type="coverage",
            polarity="covered",
        )


def test_policy_document_rejects_page_offsets_that_do_not_map_to_text():
    with pytest.raises(ValidationError, match="page offsets"):
        PolicyDocument(
            filename="policy.pdf",
            text="page one",
            pages=[
                {
                    "page_number": 1,
                    "text": "different",
                    "char_start": 0,
                    "char_end": 9,
                    "extraction_method": "pdf_text_extraction",
                }
            ],
        )


def test_typed_run_state_tracks_tasks_and_serializes_typed_findings():
    state = ClaimAnalysisRunState(request=ClaimRequestData(claim_description="A pipe burst."))
    state.set_plan(["ClaimExtractionAgent"])
    state.add(AgentResponse(agent_name="ClaimExtractionAgent", findings={"claim_type": "water_damage"}))

    serialized = state.model_dump(mode="json")
    assert state.tasks[0].status == "completed"
    assert serialized["memory"]["ClaimExtractionAgent"]["claim_type"] == "water_damage"


def test_run_state_enforces_time_and_estimated_cost_bounds():
    task = InvestigationTask(
        task_id="bounded-task",
        task_type="extract_claim",
        agent_name="ClaimExtractionAgent",
        objective="Extract claim facts.",
        expected_model_calls=1,
        estimated_cost_usd=0.01,
    )
    state = ClaimAnalysisRunState(
        request=ClaimRequestData(claim_description="A pipe burst."),
        limits=OrchestrationLimits(max_seconds=1, max_estimated_cost_usd=0.005),
    )

    allowed, reason = state.budget_allows(task)
    assert allowed is False
    assert reason == "maximum estimated cost reached"

    state.limits.max_estimated_cost_usd = 1
    state._started_at -= 2
    allowed, reason = state.budget_allows(task)
    assert allowed is False
    assert reason == "maximum orchestration time reached"

from datetime import date

import pytest
from pydantic import ValidationError

from core.agents.base import AgentContext
from core.agents.technical_agents.claim_extraction import ClaimExtractionAgent
from core.agents.technical_agents.consistency_verification import ConsistencyVerificationAgent
from core.agents.technical_agents.policy_concept_extraction import PolicyConceptExtractionAgent
from core.agents.technical_agents.shared import specialized_functional_agent_name
from core.claim_validation import extract_policy_period
from core.models.claim import ClaimRequestData, InsuranceType
from models.model_client import ModelResult


class FallbackModelClient:
    def json_response(self, **kwargs):
        return ModelResult(data=kwargs["fallback"], used_model=False)


@pytest.mark.parametrize(
    ("insurance_type", "expected_policy_type", "expected_subject_type"),
    [
        ("home", "home_insurance", "residential_property"),
        ("auto", "auto_insurance", "insured_vehicle"),
        ("travel", "travel_insurance", "insured_person_or_trip"),
    ],
)
def test_policy_concepts_are_domain_aware_and_period_dates_are_typed(
    monkeypatch,
    insurance_type,
    expected_policy_type,
    expected_subject_type,
):
    monkeypatch.setattr(
        "core.agents.technical_agents.policy_concept_extraction.get_model_client",
        lambda: FallbackModelClient(),
    )
    policy_text = "Policy period: 2026-01-01 to 31/12/2026. Covered accidental damage."
    context = AgentContext(
        request=ClaimRequestData(
            insurance_type=insurance_type,
            claim_description="An insured event occurred.",
            policy_text=policy_text,
        ),
        memory={"DocumentIngestionAgent": {"policy_text": policy_text}},
    )

    response = PolicyConceptExtractionAgent().run(context)

    assert response.findings["policy_type"] == expected_policy_type
    assert response.findings["insured_subject"]["type"] == expected_subject_type
    assert response.findings["insured_subject"]["domain"] == insurance_type
    assert response.findings["policy_period"] == {
        "start": date(2026, 1, 1),
        "end": date(2026, 12, 31),
        "status": "valid",
        "raw_start": "2026-01-01",
        "raw_end": "31/12/2026",
    }


def test_invalid_insurance_type_is_rejected_instead_of_defaulting_to_home():
    with pytest.raises(ValidationError):
        ClaimRequestData(
            insurance_type="pet",
            claim_description="My pet needed treatment.",
        )

    with pytest.raises(ValueError):
        specialized_functional_agent_name("pet")


@pytest.mark.parametrize(
    ("policy_text", "expected_status"),
    [
        ("Policy wording contains no coverage dates.", "missing"),
        ("Coverage effective 2026-01-01.", "unverifiable"),
        ("Policy period: 2026-02-30 to 2026-12-31.", "invalid"),
    ],
)
def test_policy_period_date_failures_are_distinct(policy_text, expected_status):
    assert extract_policy_period(policy_text)["status"] == expected_status


@pytest.mark.parametrize(
    ("incident_date", "policy_period", "expected_status", "expected_issue"),
    [
        (
            "2026-06-15",
            {"start": date(2026, 1, 1), "end": date(2026, 12, 31), "status": "valid"},
            "in_period",
            None,
        ),
        (
            "2027-01-01",
            {"start": date(2026, 1, 1), "end": date(2026, 12, 31), "status": "valid"},
            "out_of_period",
            "outside the policy period",
        ),
        ("2026-06-15", None, "missing_policy_period", "Policy period is missing"),
        ("not-a-date", None, "invalid_incident_date", "Incident date is invalid"),
        (
            "2026-06-15",
            {"start": date(2026, 1, 1), "end": None, "status": "unverifiable"},
            "unverifiable_policy_period",
            "incomplete or unverifiable",
        ),
    ],
)
def test_incident_date_policy_period_outcomes(
    incident_date,
    policy_period,
    expected_status,
    expected_issue,
):
    policy_findings = {
        "insured_subject": {
            "type": "residential_property",
            "domain": "home",
            "source": "policy",
            "identifiers": {},
        }
    }
    if policy_period is not None:
        policy_findings["policy_period"] = policy_period
    context = AgentContext(
        request=ClaimRequestData(
            insurance_type="home",
            claim_description="A pipe burst in the insured home.",
            incident_date=incident_date,
        ),
        memory={
            "ClaimExtractionAgent": {"claim_type": "water_damage"},
            "PolicyConceptExtractionAgent": policy_findings,
        },
    )

    response = ConsistencyVerificationAgent().run(context)

    assert response.findings["date_validation"]["comparison_status"] == expected_status
    if expected_issue:
        assert any(expected_issue in issue for issue in response.findings["consistency_issues"])
        assert response.requires_human_review is True
    else:
        assert response.findings["consistency_issues"] == []
        assert response.requires_human_review is False


def test_missing_incident_date_is_distinct_from_missing_policy_period():
    context = AgentContext(
        request=ClaimRequestData(insurance_type="home", claim_description="A pipe burst."),
        memory={
            "ClaimExtractionAgent": {"claim_type": "water_damage"},
            "PolicyConceptExtractionAgent": {
                "policy_period": {"start": None, "end": None, "status": "missing"},
                "insured_subject": {"domain": "home", "identifiers": {}},
            },
        },
    )

    validation = ConsistencyVerificationAgent().run(context).findings["date_validation"]

    assert validation["incident_date"]["status"] == "missing"
    assert validation["policy_period"]["status"] == "missing"
    assert validation["comparison_status"] == "missing_incident_date"


def test_claim_subject_domain_mismatch_is_flagged_when_claim_type_is_definitive():
    context = AgentContext(
        request=ClaimRequestData(
            insurance_type="auto",
            claim_description="A pipe burst and flooded my kitchen.",
            incident_date="2026-06-15",
        ),
        memory={
            "ClaimExtractionAgent": {"claim_type": "water_damage"},
            "PolicyConceptExtractionAgent": {
                "policy_period": {
                    "start": date(2026, 1, 1),
                    "end": date(2026, 12, 31),
                    "status": "valid",
                },
                "insured_subject": {"domain": "auto", "identifiers": {}},
            },
        },
    )

    response = ConsistencyVerificationAgent().run(context)

    assert response.findings["insured_subject_consistency"]["status"] == "inconsistent"
    assert any("home insured subject" in issue for issue in response.findings["consistency_issues"])


def test_insured_vehicle_identifier_mismatch_is_flagged():
    context = AgentContext(
        request=ClaimRequestData(
            insurance_type="auto",
            claim_description="My car with registration BG-999-ZZ was damaged in a collision.",
            incident_date="2026-06-15",
        ),
        memory={
            "ClaimExtractionAgent": {"claim_type": "vehicle_damage"},
            "PolicyConceptExtractionAgent": {
                "policy_period": {
                    "start": date(2026, 1, 1),
                    "end": date(2026, 12, 31),
                    "status": "valid",
                },
                "insured_subject": {
                    "domain": "auto",
                    "identifiers": {"registration": "BG123AA"},
                },
            },
        },
    )

    response = ConsistencyVerificationAgent().run(context)

    assert response.findings["insured_subject_consistency"]["status"] == "inconsistent"
    assert any("registration does not match" in issue for issue in response.findings["consistency_issues"])


def test_model_cannot_overwrite_explicit_incident_date_and_trip_cancellation_is_in_schema(monkeypatch):
    class OverwritingModelClient:
        def json_response(self, **kwargs):
            assert "trip_cancellation" in kwargs["prompt"]
            return ModelResult(
                data={
                    **kwargs["fallback"],
                    "claim_type": "trip_cancellation",
                    "incident_date": "2099-12-31",
                },
                used_model=True,
            )

    monkeypatch.setattr(
        "core.agents.technical_agents.claim_extraction.get_model_client",
        lambda: OverwritingModelClient(),
    )
    context = AgentContext(
        request=ClaimRequestData(
            insurance_type=InsuranceType.TRAVEL,
            claim_description="I cancelled my trip after becoming ill.",
            incident_date="2026-06-15",
        )
    )

    response = ClaimExtractionAgent().run(context)

    assert response.findings["claim_type"] == "trip_cancellation"
    assert response.findings["incident_date"] == "2026-06-15"


def test_trip_cancellation_is_supported_by_deterministic_claim_classification(monkeypatch):
    monkeypatch.setattr(
        "core.agents.technical_agents.claim_extraction.get_model_client",
        lambda: FallbackModelClient(),
    )
    context = AgentContext(
        request=ClaimRequestData(
            insurance_type="travel",
            claim_description="The airline cancelled my trip before departure.",
        )
    )

    response = ClaimExtractionAgent().run(context)

    assert response.findings["claim_type"] == "trip_cancellation"

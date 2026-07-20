import pytest
from pydantic import ValidationError

from core.models.claim import ClaimAnalysisResult, ClaimStatus, CoverageAssessment, ImageAuthenticity, RiskLevel


def test_risk_level_serializes_as_api_string():
    assessment = ImageAuthenticity(risk_level=RiskLevel.HIGH)

    assert assessment.model_dump(mode="json")["risk_level"] == "high"


def test_risk_level_accepts_known_string_value():
    assessment = ImageAuthenticity(risk_level="requires_human_review")

    assert assessment.risk_level is RiskLevel.REQUIRES_HUMAN_REVIEW


def test_risk_level_rejects_unknown_value():
    with pytest.raises(ValidationError):
        ImageAuthenticity(risk_level="critical")


def test_claim_enums_serialize_as_api_strings():
    result = ClaimAnalysisResult(
        claim_status=ClaimStatus.REQUIRES_HUMAN_REVIEW,
        insurance_type="home",
        claim_type="water_damage",
        coverage_assessment=CoverageAssessment.UNCLEAR,
        reasoning_summary="Review required.",
        recommendation="Review.",
    )

    serialized = result.model_dump(mode="json")
    assert serialized["claim_status"] == "requires_human_review"
    assert serialized["coverage_assessment"] == "unclear"

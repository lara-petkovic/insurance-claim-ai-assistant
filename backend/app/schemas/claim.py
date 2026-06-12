from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.agent import AgentResponse, EvidenceItem


ClaimStatus = Literal[
    "likely_covered",
    "likely_not_covered",
    "partially_covered",
    "requires_human_review",
]

CoverageAssessment = Literal[
    "covered",
    "not_covered",
    "possibly_covered",
    "unclear",
]


class ClaimRequestData(BaseModel):
    insurance_type: str = "home"
    claim_description: str
    incident_date: str | None = None
    policy_text: str = ""
    policy_filename: str | None = None
    damage_image_filename: str | None = None
    damage_image_size: int | None = None
    damage_image_mime_type: str | None = None
    damage_image_bytes: bytes | None = Field(default=None, exclude=True)
    supporting_document_names: list[str] = Field(default_factory=list)


class ImageAssessment(BaseModel):
    detected_damage: str = "unknown"
    confidence: float = 0.0
    notes: list[str] = Field(default_factory=list)


class ImageAuthenticity(BaseModel):
    risk_level: Literal["low", "medium", "high", "requires_human_review"] = "low"
    risk_score: float = 0.0
    signals: list[str] = Field(default_factory=list)


class ClaimAnalysisResult(BaseModel):
    claim_status: ClaimStatus
    insurance_type: str
    claim_type: str
    coverage_assessment: CoverageAssessment
    matched_policy_concepts: list[dict[str, Any]] = Field(default_factory=list)
    potential_exclusions: list[dict[str, Any]] = Field(default_factory=list)
    missing_documents: list[str] = Field(default_factory=list)
    image_assessment: ImageAssessment = Field(default_factory=ImageAssessment)
    image_authenticity: ImageAuthenticity = Field(default_factory=ImageAuthenticity)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    reasoning_summary: str
    recommendation: str
    agent_trace: list[AgentResponse] = Field(default_factory=list)


class DocumentExtractionResult(BaseModel):
    filename: str
    document_type: str
    text: str
    warnings: list[str] = Field(default_factory=list)

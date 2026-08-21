from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from core.models.agent import AgentResponse, EvidenceItem
from core.models.analysis import (
    AssessmentProposition,
    ClaimFact,
    DocumentPage,
    PolicyClause,
    PolicyDocument,
    SupportingDocument,
)


class InsuranceType(StrEnum):
    HOME = "home"
    AUTO = "auto"
    TRAVEL = "travel"


class ClaimStatus(StrEnum):
    LIKELY_COVERED = "likely_covered"
    LIKELY_NOT_COVERED = "likely_not_covered"
    PARTIALLY_COVERED = "partially_covered"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"


class CoverageAssessment(StrEnum):
    COVERED = "covered"
    NOT_COVERED = "not_covered"
    POSSIBLY_COVERED = "possibly_covered"
    UNCLEAR = "unclear"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"


class SupportingDocumentData(SupportingDocument):
    """Backward-compatible API name for the typed supporting document model."""


class ClaimRequestData(BaseModel):
    insurance_type: InsuranceType = InsuranceType.HOME
    claim_description: str
    incident_date: str | None = None
    policy_text: str = ""
    policy_filename: str | None = None
    policy_extraction_warnings: list[str] = Field(default_factory=list)
    policy_document: PolicyDocument | None = None
    damage_image_filename: str | None = None
    damage_image_size: int | None = None
    damage_image_mime_type: str | None = None
    damage_image_bytes: bytes | None = Field(default=None, exclude=True)
    supporting_documents: list[SupportingDocumentData] = Field(default_factory=list)
    security_flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def synchronize_policy_views(self) -> ClaimRequestData:
        """Keep the legacy policy fields and typed document representation aligned."""
        if self.policy_document is None and (self.policy_filename or self.policy_text):
            self.policy_document = PolicyDocument(
                filename=self.policy_filename or "policy",
                text=self.policy_text,
                extraction_warnings=self.policy_extraction_warnings,
            )
        elif self.policy_document is not None:
            self.policy_text = self.policy_document.text
            self.policy_filename = self.policy_document.filename
            self.policy_extraction_warnings = list(self.policy_document.extraction_warnings)
        return self

    @property
    def supporting_document_names(self) -> list[str]:
        """Backward-compatible view; new code should use supporting_documents."""
        return [document.filename for document in self.supporting_documents]


class ImageAssessment(BaseModel):
    detected_damage: str = "unknown"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class ImageAuthenticity(BaseModel):
    risk_level: RiskLevel = RiskLevel.LOW
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    signals: list[str] = Field(default_factory=list)


class ClaimAnalysisResult(BaseModel):
    claim_status: ClaimStatus
    insurance_type: InsuranceType
    claim_type: str
    coverage_assessment: CoverageAssessment
    matched_policy_concepts: list[dict[str, Any]] = Field(default_factory=list)
    potential_exclusions: list[dict[str, Any]] = Field(default_factory=list)
    missing_documents: list[str] = Field(default_factory=list)
    image_assessment: ImageAssessment = Field(default_factory=ImageAssessment)
    image_authenticity: ImageAuthenticity = Field(default_factory=ImageAuthenticity)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    claim_facts: list[ClaimFact] = Field(default_factory=list)
    policy_clauses: list[PolicyClause] = Field(default_factory=list)
    assessment_propositions: list[AssessmentProposition] = Field(default_factory=list)
    reasoning_summary: str
    recommendation: str
    security_flags: list[str] = Field(default_factory=list)
    agent_trace: list[AgentResponse] = Field(default_factory=list)


class DocumentExtractionResult(BaseModel):
    filename: str
    document_type: str
    text: str
    warnings: list[str] = Field(default_factory=list)
    document_id: str | None = None
    pages: list[DocumentPage] = Field(default_factory=list)
    extraction_method: str | None = None

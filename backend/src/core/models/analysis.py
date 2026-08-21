"""Typed intermediate claim-analysis models and evidence provenance."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from enum import StrEnum
import hashlib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


UnitInterval = float


class ExtractionMethod(StrEnum):
    USER_INPUT = "user_input"
    TEXT = "text_extraction"
    PDF_TEXT = "pdf_text_extraction"
    PDF_VISION = "pdf_vision_extraction"
    MODEL = "model_extraction"
    RULE = "rule_extraction"
    RETRIEVAL = "retrieval"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    MACHINE_VERIFIED = "machine_verified"
    HUMAN_VERIFIED = "human_verified"
    REJECTED = "rejected"


class ClauseType(StrEnum):
    COVERAGE = "coverage"
    EXCLUSION = "exclusion"
    CONDITION = "condition"
    LIMIT = "limit"
    DEDUCTIBLE = "deductible"
    DEFINITION = "definition"
    REQUIREMENT = "requirement"
    OTHER = "other"


class ClausePolarity(StrEnum):
    COVERED = "covered"
    EXCLUDED = "excluded"
    CONDITIONAL = "conditional"
    NEUTRAL = "neutral"
    UNCLEAR = "unclear"


class DocumentPage(BaseModel):
    """One extracted page positioned inside the document's combined text."""

    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    text: str
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    extraction_method: ExtractionMethod

    @model_validator(mode="after")
    def validate_span(self) -> DocumentPage:
        if self.char_end < self.char_start:
            raise ValueError("char_end must be greater than or equal to char_start")
        if self.char_end - self.char_start != len(self.text):
            raise ValueError("page character offsets must span the extracted page text")
        return self


class SourceDocument(BaseModel):
    """Common, provenance-preserving representation of an extracted document."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = ""
    filename: str = Field(min_length=1)
    document_type: str = Field(min_length=1)
    text: str = ""
    pages: list[DocumentPage] = Field(default_factory=list)
    extraction_method: ExtractionMethod = ExtractionMethod.TEXT
    extraction_warnings: list[str] = Field(default_factory=list)
    text_length: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def normalize_length(self) -> SourceDocument:
        if not self.document_id:
            digest = hashlib.sha256(
                self.filename.encode("utf-8") + b"\0" + self.text.encode("utf-8")
            ).hexdigest()[:20]
            self.document_id = f"doc_{digest}"
        self.text_length = len(self.text)
        previous_end = 0
        previous_page_number = 0
        for page in self.pages:
            if page.page_number <= previous_page_number:
                raise ValueError("document pages must have unique ascending page numbers")
            if page.char_start < previous_end or page.char_end > len(self.text):
                raise ValueError("page offsets must be ordered and within the document text")
            if self.text[page.char_start : page.char_end] != page.text:
                raise ValueError("page offsets do not map to the combined document text")
            previous_end = page.char_end
            previous_page_number = page.page_number
        return self


class PolicyDocument(SourceDocument):
    document_type: Literal["policy"] = "policy"


class SupportingDocument(SourceDocument):
    pass


class ProvenancedExcerpt(BaseModel):
    """Exact source excerpt with a stable source location."""

    model_config = ConfigDict(extra="forbid")

    source_document_id: str = Field(min_length=1)
    source_filename: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    section_heading: str | None = None
    evidence_text: str = Field(min_length=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    stable_location: str = Field(min_length=1)
    extraction_method: ExtractionMethod
    confidence: UnitInterval = Field(default=1.0, ge=0.0, le=1.0)
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED

    @model_validator(mode="after")
    def validate_offsets(self) -> ProvenancedExcerpt:
        if (self.char_start is None) != (self.char_end is None):
            raise ValueError("char_start and char_end must be supplied together")
        if self.char_start is not None and self.char_end is not None:
            if self.char_end < self.char_start:
                raise ValueError("char_end must be greater than or equal to char_start")
            if self.char_end - self.char_start != len(self.evidence_text):
                raise ValueError("character offsets must span the exact evidence text")
        return self

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class EvidenceReference(ProvenancedExcerpt):
    """A reusable evidence citation for propositions and agent responses."""


class PolicyClause(ProvenancedExcerpt):
    clause_id: str = Field(min_length=1)
    concept: str = Field(min_length=1)
    clause_type: ClauseType
    polarity: ClausePolarity
    matched_terms: list[str] = Field(default_factory=list)
    direct_match: bool = False


class ClaimFact(ProvenancedExcerpt):
    fact_id: str = Field(min_length=1)
    fact_type: str = Field(min_length=1)
    value: str | int | float | bool | None = None


class PropositionStatus(StrEnum):
    PROPOSED = "proposed"
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INCONCLUSIVE = "inconclusive"


class AssessmentProposition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposition_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    status: PropositionStatus = PropositionStatus.PROPOSED
    evidence: list[EvidenceReference] = Field(default_factory=list)
    confidence: UnitInterval = Field(default=0.0, ge=0.0, le=1.0)
    created_by: str = Field(min_length=1)


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class InvestigationTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    status: TaskStatus = TaskStatus.PENDING
    depends_on: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


AgentTask = InvestigationTask


class AgentFindings(BaseModel, Mapping[str, Any]):
    """Typed findings base that retains the legacy dictionary read interface."""

    model_config = ConfigDict(extra="allow")

    def __getitem__(self, key: str) -> Any:
        if key in type(self).model_fields:
            return getattr(self, key)
        extra = self.__pydantic_extra__ or {}
        if key in extra:
            return extra[key]
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        yield from self.model_dump().keys()

    def __len__(self) -> int:
        return len(self.model_dump())

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


class GenericAgentFindings(AgentFindings):
    pass


class UserProvidedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    has_image: bool
    supporting_documents: list[SupportingDocumentSummary]


class SupportingDocumentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    document_type: str


class ClaimExtractionModelOutput(BaseModel):
    """Strict schema emitted by the claim extraction model."""

    model_config = ConfigDict(extra="forbid")

    claim_type: Literal[
        "water_damage", "storm_damage", "theft", "fire_damage", "broken_glass",
        "vehicle_damage", "medical", "baggage_loss", "trip_cancellation", "unknown",
    ]
    incident_date: str | None
    incident_location: str
    damage_or_loss_type: str
    claimed_cause: str
    claimed_amount: str | None
    user_provided_evidence: UserProvidedEvidence


class ClaimExtractionFindings(ClaimExtractionModelOutput, AgentFindings):
    facts: list[ClaimFact] = Field(default_factory=list)
    model_used: bool = False


class PolicyConceptItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept: str
    evidence_text: str


class PolicyPeriodModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str | None
    end: str | None
    status: Literal["valid", "invalid", "missing", "unverifiable"]
    raw_start: str | None
    raw_end: str | None


class SubjectIdentifiersModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vin: str | None
    registration: str | None
    property_address: str | None
    booking_reference: str | None


class InsuredSubjectModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    domain: str
    source: str
    identifiers: SubjectIdentifiersModelOutput


class PolicyExtractionModelOutput(BaseModel):
    """Strict schema emitted by the policy concept extraction model."""

    model_config = ConfigDict(extra="forbid")

    policy_type: str
    policy_period: PolicyPeriodModelOutput
    insured_subject: InsuredSubjectModelOutput
    covered_events: list[PolicyConceptItem]
    exclusions: list[PolicyConceptItem]
    limits: list[str]
    deductible_or_excess: str | None
    required_claim_documents: list[str]
    special_conditions: list[str]


class PolicyExtractionFindings(AgentFindings):
    policy_type: str
    policy_period: dict[str, Any]
    insured_subject: dict[str, Any]
    covered_events: list[dict[str, Any]] = Field(default_factory=list)
    coverage_clauses: list[PolicyClause] = Field(default_factory=list)
    exclusions: list[dict[str, Any]] = Field(default_factory=list)
    limits: list[Any] = Field(default_factory=list)
    deductible_or_excess: str | None = None
    required_claim_documents: list[str] = Field(default_factory=list)
    special_conditions: list[str] = Field(default_factory=list)
    model_used: bool = False


class VisualEvidenceModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detected_damage: Literal[
        "water_damage", "fire_damage", "storm_damage", "broken_glass",
        "theft_damage", "vehicle_damage", "unknown",
    ]
    confidence: UnitInterval = Field(ge=0.0, le=1.0)
    notes: list[str] = Field(max_length=20)


class VisualEvidenceFindings(VisualEvidenceModelOutput, AgentFindings):
    model_used: bool = False


class ImageIntegrityModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_level: Literal["low", "medium", "high", "requires_human_review"]
    risk_score: UnitInterval = Field(ge=0.0, le=1.0)
    signals: list[str] = Field(max_length=20)


class ImageIntegrityFindings(ImageIntegrityModelOutput, AgentFindings):
    model_used: bool = False


class CoverageModelMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept: str = Field(max_length=100)
    evidence_text: str = Field(max_length=2_000)


class CoverageModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coverage_assessment: Literal["covered", "not_covered", "possibly_covered", "unclear"]
    matched_policy_concepts: list[CoverageModelMatch] = Field(max_length=20)
    explanation: str = Field(max_length=4_000)
    suspected_prompt_injection: bool


class CoverageFindings(AgentFindings):
    coverage_assessment: Literal["covered", "not_covered", "possibly_covered", "unclear"]
    matched_policy_concepts: list[dict[str, Any]] = Field(default_factory=list)
    supporting_policy_passages: list[str] = Field(default_factory=list)
    clause_polarities: list[str] = Field(default_factory=list)
    functional_checks_considered: list[Any] = Field(default_factory=list)
    explanation: str = ""
    suspected_prompt_injection: bool = False
    model_used: bool = False


class ExclusionModelItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept: str = Field(max_length=100)
    severity: Literal["low", "medium", "high"]
    reason: str = Field(max_length=2_000)
    evidence_text: str = Field(max_length=2_000)


class ExclusionModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    potential_exclusions: list[ExclusionModelItem] = Field(max_length=20)
    suspected_prompt_injection: bool


class ExclusionFindings(AgentFindings):
    potential_exclusions: list[dict[str, Any]] = Field(default_factory=list)
    targeted_checks: list[Any] = Field(default_factory=list)
    suspected_prompt_injection: bool = False
    model_used: bool = False


class PlanningSignalsModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_theme: Literal[
        "theft", "storm_damage", "water_damage", "fire_damage", "vehicle_damage",
        "medical", "baggage_loss", "trip_cancellation", "unknown",
    ]
    evidence_focus: list[str] = Field(max_length=5)
    rationale: str


class PlanningSignalsFindings(PlanningSignalsModelOutput, AgentFindings):
    model_used: bool
    model_name: str
    model_error: str | None


class DynamicPlanningFindings(AgentFindings):
    planned_agents: list[str]
    skipped_agents: list[str]
    rationale: list[str]
    planning_mode: str
    planning_signals: PlanningSignalsFindings


class PdfPageModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    text: str


class PdfExtractionModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pages: list[PdfPageModelOutput]
    warnings: list[str] = Field(max_length=8)

    @model_validator(mode="after")
    def validate_page_order(self) -> PdfExtractionModelOutput:
        page_numbers = [page.page_number for page in self.pages]
        if page_numbers != sorted(set(page_numbers)):
            raise ValueError("PDF pages must have unique ascending page numbers")
        return self


__all__ = [
    "AgentFindings", "AgentTask", "AssessmentProposition", "ClaimExtractionFindings",
    "ClaimExtractionModelOutput", "ClaimFact", "ClausePolarity", "ClauseType",
    "CoverageFindings", "CoverageModelOutput", "DocumentPage", "EvidenceReference",
    "ExclusionFindings", "ExclusionModelOutput",
    "ExtractionMethod", "GenericAgentFindings", "ImageIntegrityFindings",
    "ImageIntegrityModelOutput", "InvestigationTask", "PdfExtractionModelOutput",
    "DynamicPlanningFindings", "PlanningSignalsFindings", "PlanningSignalsModelOutput",
    "PolicyClause", "PolicyDocument", "PolicyExtractionFindings",
    "PolicyExtractionModelOutput", "PropositionStatus", "SourceDocument",
    "SupportingDocument", "TaskStatus", "VerificationStatus", "VisualEvidenceFindings",
    "VisualEvidenceModelOutput",
]

"""Technical agents execute concrete analysis tasks.

Each technical agent knows its own responsibility and performs that task using
the shared context, extracted data, model calls, retrieval evidence, validation
rules, or image inputs as needed.
"""

from core.agents.technical_agents.documents import DocumentIngestionAgent, DocumentQualityAgent
from core.agents.technical_agents.extraction import ClaimExtractionAgent, PolicyConceptExtractionAgent
from core.agents.technical_agents.retrieval import QueryRewriteAgent, RetrievalAgent
from core.agents.technical_agents.vision import ImageAuthenticityAgent, VisualEvidenceAgent
from core.agents.technical_agents.coverage import CoverageMatchingAgent
from core.agents.technical_agents.validation import (
    CitationAgent,
    ConsistencyVerificationAgent,
    ExclusionCheckingAgent,
    MissingDocumentsAgent,
    OutputValidatorAgent,
)

__all__ = [
    "DocumentIngestionAgent",
    "DocumentQualityAgent",
    "PolicyConceptExtractionAgent",
    "ClaimExtractionAgent",
    "QueryRewriteAgent",
    "RetrievalAgent",
    "VisualEvidenceAgent",
    "ImageAuthenticityAgent",
    "CoverageMatchingAgent",
    "ExclusionCheckingAgent",
    "MissingDocumentsAgent",
    "ConsistencyVerificationAgent",
    "CitationAgent",
    "OutputValidatorAgent",
]

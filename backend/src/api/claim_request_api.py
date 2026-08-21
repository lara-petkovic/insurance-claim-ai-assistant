"""HTTP endpoints for claim requests, document extraction, and service health."""

from __future__ import annotations

import json
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from services.claim_request_builder import (
    build_claim_request,
    read_bounded_upload,
    validate_upload_suffix,
)
from core.agents import OrchestratorAgent
from core.models.claim import ClaimAnalysisResult, ClaimRequestData, DocumentExtractionResult, InsuranceType
from data.text_extraction import extract_upload_text, infer_document_type
from security.input_security import ALLOWED_SUPPORTING_SUFFIXES, MAX_SUPPORTING_FILE_BYTES
from utils.app_logger import get_logger

router = APIRouter(prefix="/api")
logger = get_logger("api.streaming")


@lru_cache(maxsize=1)
def get_orchestrator() -> OrchestratorAgent:
    return OrchestratorAgent()


async def get_claim_request(
    insurance_type: Annotated[InsuranceType, Form()] = InsuranceType.HOME,
    claim_description: Annotated[str, Form()] = "",
    incident_date: Annotated[str | None, Form()] = None,
    policy_file: Annotated[UploadFile | None, File()] = None,
    damage_image: Annotated[UploadFile | None, File()] = None,
    supporting_documents: Annotated[list[UploadFile] | None, File()] = None,
) -> ClaimRequestData:
    return await build_claim_request(
        insurance_type=insurance_type,
        claim_description=claim_description,
        incident_date=incident_date,
        policy_file=policy_file,
        damage_image=damage_image,
        supporting_documents=supporting_documents,
    )


ClaimRequest = Annotated[ClaimRequestData, Depends(get_claim_request)]
Orchestrator = Annotated[OrchestratorAgent, Depends(get_orchestrator)]


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/documents/extract", response_model=DocumentExtractionResult)
async def extract_document(file: Annotated[UploadFile, File(...)]) -> DocumentExtractionResult:
    validate_upload_suffix(file.filename or "", ALLOWED_SUPPORTING_SUFFIXES)
    content = await read_bounded_upload(file, MAX_SUPPORTING_FILE_BYTES)
    filename = file.filename or "uploaded_file"
    extraction = await extract_upload_text(filename, content)
    text, warnings = extraction
    document = getattr(extraction, "document", None)
    return DocumentExtractionResult(
        filename=filename,
        document_type=infer_document_type(filename),
        text=text,
        warnings=warnings,
        document_id=getattr(document, "document_id", None),
        pages=getattr(document, "pages", []),
        extraction_method=getattr(document, "extraction_method", None),
    )


@router.post("/claims/analyze", response_model=ClaimAnalysisResult)
async def analyze_claim(request: ClaimRequest, orchestrator: Orchestrator) -> ClaimAnalysisResult:
    return orchestrator.analyze(request)


@router.post("/claims/analyze-stream")
async def analyze_claim_stream(
    request: ClaimRequest,
    orchestrator: Orchestrator,
) -> StreamingResponse:
    return StreamingResponse(
        _stream_claim_analysis(orchestrator, request),
        media_type="application/x-ndjson",
    )


def _stream_claim_analysis(
    orchestrator: OrchestratorAgent,
    request: ClaimRequestData,
) -> Iterator[str]:
    try:
        for event in orchestrator.stream(request):
            yield _encode_event(event)
    except Exception:
        logger.exception("Claim analysis stream failed.")
        yield _encode_event(
            {
                "event": "analysis_failed",
                "error": "Claim analysis failed. Please retry or request human review.",
            }
        )


def _encode_event(event: dict[str, Any]) -> str:
    return json.dumps(event) + "\n"

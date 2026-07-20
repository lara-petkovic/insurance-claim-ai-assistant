from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from core.agents import OrchestratorAgent
from core.models.claim import ClaimAnalysisResult, ClaimRequestData, DocumentExtractionResult, SupportingDocumentData
from data.text_extraction import extract_upload_text, infer_document_type
from security.input_security import (
    ALLOWED_IMAGE_MIME_TYPES,
    ALLOWED_POLICY_SUFFIXES,
    ALLOWED_SUPPORTING_SUFFIXES,
    MAX_CLAIM_DESCRIPTION_CHARS,
    MAX_EXTRACTED_TEXT_CHARS,
    MAX_IMAGE_BYTES,
    MAX_POLICY_BYTES,
    MAX_SUPPORTING_DOCUMENTS,
    MAX_SUPPORTING_FILE_BYTES,
    detect_prompt_injection,
)

router = APIRouter(prefix="/api")
orchestrator = OrchestratorAgent()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/documents/extract", response_model=DocumentExtractionResult)
async def extract_document(file: Annotated[UploadFile, File(...)]) -> DocumentExtractionResult:
    _validate_suffix(file.filename or "", ALLOWED_SUPPORTING_SUFFIXES)
    content = await _read_bounded(file, MAX_SUPPORTING_FILE_BYTES)
    text, warnings = await extract_upload_text(file.filename or "uploaded_file", content)
    return DocumentExtractionResult(
        filename=file.filename or "uploaded_file",
        document_type=infer_document_type(file.filename or ""),
        text=text,
        warnings=warnings,
    )


@router.post("/claims/analyze", response_model=ClaimAnalysisResult)
async def analyze_claim(
    insurance_type: Annotated[str, Form()] = "home",
    claim_description: Annotated[str, Form()] = "",
    incident_date: Annotated[str | None, Form()] = None,
    policy_file: Annotated[UploadFile | None, File()] = None,
    damage_image: Annotated[UploadFile | None, File()] = None,
    supporting_documents: Annotated[list[UploadFile] | None, File()] = None,
) -> ClaimAnalysisResult:
    request = await _build_claim_request(
        insurance_type=insurance_type,
        claim_description=claim_description,
        incident_date=incident_date,
        policy_file=policy_file,
        damage_image=damage_image,
        supporting_documents=supporting_documents,
    )
    return orchestrator.analyze(request)


@router.post("/claims/analyze-stream")
async def analyze_claim_stream(
    insurance_type: Annotated[str, Form()] = "home",
    claim_description: Annotated[str, Form()] = "",
    incident_date: Annotated[str | None, Form()] = None,
    policy_file: Annotated[UploadFile | None, File()] = None,
    damage_image: Annotated[UploadFile | None, File()] = None,
    supporting_documents: Annotated[list[UploadFile] | None, File()] = None,
) -> StreamingResponse:
    request = await _build_claim_request(
        insurance_type=insurance_type,
        claim_description=claim_description,
        incident_date=incident_date,
        policy_file=policy_file,
        damage_image=damage_image,
        supporting_documents=supporting_documents,
    )

    def event_stream():
        try:
            for event in orchestrator.stream(request):
                yield json.dumps(event) + "\n"
        except Exception as exc:
            yield json.dumps({"event": "analysis_failed", "error": str(exc)}) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


async def _build_claim_request(
    insurance_type: str,
    claim_description: str,
    incident_date: str | None,
    policy_file: UploadFile | None,
    damage_image: UploadFile | None,
    supporting_documents: list[UploadFile] | None,
) -> ClaimRequestData:
    if len(claim_description) > MAX_CLAIM_DESCRIPTION_CHARS:
        raise HTTPException(status_code=413, detail="Claim description is too large.")
    if len(supporting_documents or []) > MAX_SUPPORTING_DOCUMENTS:
        raise HTTPException(status_code=413, detail=f"At most {MAX_SUPPORTING_DOCUMENTS} supporting documents are allowed.")
    security_flags = [f"claim_description:{flag}" for flag in detect_prompt_injection(claim_description)]
    policy_text = ""
    policy_filename = None
    policy_extraction_warnings: list[str] = []
    if policy_file:
        _validate_suffix(policy_file.filename or "", ALLOWED_POLICY_SUFFIXES)
        policy_filename = policy_file.filename
        policy_text, policy_extraction_warnings = await extract_upload_text(
            policy_file.filename or "policy.pdf",
            await _read_bounded(policy_file, MAX_POLICY_BYTES),
        )
        policy_text = policy_text[:MAX_EXTRACTED_TEXT_CHARS]
        security_flags.extend(f"policy:{flag}" for flag in detect_prompt_injection(policy_text))
    if not policy_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Policy text is required. Upload a PDF or text policy document that can be extracted by text or vision fallback.",
        )

    damage_image_filename = None
    damage_image_size = None
    damage_image_mime_type = None
    damage_image_bytes = None
    if damage_image:
        if damage_image.content_type not in ALLOWED_IMAGE_MIME_TYPES:
            raise HTTPException(status_code=415, detail="Unsupported damage image type.")
        damage_image_filename = damage_image.filename
        damage_image_mime_type = damage_image.content_type
        damage_image_bytes = await _read_bounded(damage_image, MAX_IMAGE_BYTES)
        damage_image_size = len(damage_image_bytes)

    extracted_supporting_documents: list[SupportingDocumentData] = []
    for document in supporting_documents or []:
        filename = document.filename or "supporting_document"
        _validate_suffix(filename, ALLOWED_SUPPORTING_SUFFIXES)
        text = ""
        warnings: list[str] = []
        try:
            content = await _read_bounded(document, MAX_SUPPORTING_FILE_BYTES)
            text, warnings = await extract_upload_text(filename, content)
            text = text[:MAX_EXTRACTED_TEXT_CHARS]
            security_flags.extend(f"supporting_document:{flag}" for flag in detect_prompt_injection(text))
            if not text.strip() and not warnings:
                warnings.append("Supporting document extraction returned no usable text.")
        except Exception as exc:
            warnings.append(f"Supporting document extraction failed: {exc}")
        extracted_supporting_documents.append(
            SupportingDocumentData(
                filename=filename,
                document_type=infer_document_type(filename),
                text=text,
                extraction_warnings=warnings,
                text_length=len(text),
            )
        )

    return ClaimRequestData(
        insurance_type=insurance_type,
        claim_description=claim_description,
        incident_date=incident_date,
        policy_text=policy_text,
        policy_filename=policy_filename,
        policy_extraction_warnings=policy_extraction_warnings,
        damage_image_filename=damage_image_filename,
        damage_image_size=damage_image_size,
        damage_image_mime_type=damage_image_mime_type,
        damage_image_bytes=damage_image_bytes,
        supporting_documents=extracted_supporting_documents,
        security_flags=sorted(set(security_flags)),
    )


async def _read_bounded(file: UploadFile, limit: int) -> bytes:
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(status_code=413, detail=f"Uploaded file exceeds the {limit // (1024 * 1024)} MB limit.")
    return content


def _validate_suffix(filename: str, allowed: set[str]) -> None:
    if Path(filename).suffix.lower() not in allowed:
        raise HTTPException(status_code=415, detail="Unsupported file type.")

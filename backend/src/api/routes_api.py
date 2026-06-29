from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from core.agents import OrchestratorAgent
from core.models.claim import ClaimAnalysisResult, ClaimRequestData, DocumentExtractionResult
from data.text_extraction import extract_upload_text, infer_document_type

router = APIRouter(prefix="/api")
orchestrator = OrchestratorAgent()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/documents/extract", response_model=DocumentExtractionResult)
async def extract_document(file: Annotated[UploadFile, File(...)]) -> DocumentExtractionResult:
    content = await file.read()
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
    policy_text = ""
    policy_filename = None
    if policy_file:
        policy_filename = policy_file.filename
        policy_text, _ = await extract_upload_text(policy_file.filename or "policy.pdf", await policy_file.read())
    if not policy_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Policy text is required. Upload a text-based PDF or .txt policy document that can be extracted.",
        )

    damage_image_filename = None
    damage_image_size = None
    damage_image_mime_type = None
    damage_image_bytes = None
    if damage_image:
        damage_image_filename = damage_image.filename
        damage_image_mime_type = damage_image.content_type
        damage_image_bytes = await damage_image.read()
        damage_image_size = len(damage_image_bytes)

    supporting_document_names = []
    if supporting_documents:
        supporting_document_names = [doc.filename or "supporting_document" for doc in supporting_documents]

    return ClaimRequestData(
        insurance_type=insurance_type,
        claim_description=claim_description,
        incident_date=incident_date,
        policy_text=policy_text,
        policy_filename=policy_filename,
        damage_image_filename=damage_image_filename,
        damage_image_size=damage_image_size,
        damage_image_mime_type=damage_image_mime_type,
        damage_image_bytes=damage_image_bytes,
        supporting_document_names=supporting_document_names,
    )

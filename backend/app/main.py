from __future__ import annotations

import json
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.agents.orchestrator import OrchestratorAgent
from app.schemas.claim import ClaimAnalysisResult, ClaimRequestData, DocumentExtractionResult
from app.services.model_client import ModelCallError, get_model_client
from app.services.text_extraction import extract_upload_text, infer_document_type

app = FastAPI(
    title="Insurance Claim Multi-Agent Assessment API",
    version="0.1.0",
    description="Explainable techno-functional multi-agent prototype for insurance claim eligibility assessment.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = OrchestratorAgent()


class ModelTestRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    system: str | None = None
    model: str | None = None


class ModelTestResponse(BaseModel):
    provider: str
    model: str
    used_model: bool
    answer: str


@app.exception_handler(ModelCallError)
async def model_call_error_handler(_, exc: ModelCallError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Model-backed agents are required, but a model call failed.",
            "error": str(exc),
            "hint": "Check backend/.env, OPENAI_API_KEY, selected OpenAI model names, billing, and model access.",
        },
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/agents")
def agents() -> dict[str, list[str]]:
    return {"agents": [agent.name for agent in orchestrator.agents]}


@app.get("/api/model-status")
def model_status() -> dict[str, object]:
    return get_model_client().status()


@app.post("/api/model-test", response_model=ModelTestResponse)
def model_test(request: ModelTestRequest) -> ModelTestResponse:
    client = get_model_client()
    result = client.text_response(prompt=request.prompt, system=request.system, model=request.model)
    selected_model = request.model or client.text_model
    return ModelTestResponse(
        provider=client.provider,
        model=selected_model,
        used_model=result.used_model,
        answer=str(result.data.get("answer", "")),
    )


@app.post("/api/documents/extract", response_model=DocumentExtractionResult)
async def extract_document(file: Annotated[UploadFile, File(...)]) -> DocumentExtractionResult:
    content = await file.read()
    text, warnings = await extract_upload_text(file.filename or "uploaded_file", content)
    return DocumentExtractionResult(
        filename=file.filename or "uploaded_file",
        document_type=infer_document_type(file.filename or ""),
        text=text,
        warnings=warnings,
    )


@app.post("/api/claims/analyze", response_model=ClaimAnalysisResult)
async def analyze_claim(
    insurance_type: Annotated[str, Form()] = "home",
    claim_description: Annotated[str, Form()] = "",
    incident_date: Annotated[str | None, Form()] = None,
    policy_file: Annotated[UploadFile | None, File()] = None,
    damage_image: Annotated[UploadFile | None, File()] = None,
    supporting_documents: Annotated[list[UploadFile] | None, File()] = None,
) -> ClaimAnalysisResult:
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

    request = ClaimRequestData(
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
    return orchestrator.analyze(request)


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


@app.post("/api/claims/analyze-stream")
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

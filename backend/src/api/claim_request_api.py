from __future__ import annotations

import json
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from core.agents import OrchestratorAgent
from core.models.claim import ClaimAnalysisResult, ClaimRequestData, InsuranceType
from services.claim_request_builder import build_claim_request
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


@router.post("/claims/analyze", response_model=ClaimAnalysisResult)
async def analyze_claim(request: ClaimRequest, orchestrator: Orchestrator) -> ClaimAnalysisResult:
    return orchestrator.analyze(request)


@router.post("/claims/analyze-stream")
async def analyze_claim_stream(request: ClaimRequest, orchestrator: Orchestrator) -> StreamingResponse:
    def stream_events() -> Iterator[str]:
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

    return StreamingResponse(stream_events(), media_type="application/x-ndjson")


def _encode_event(event: dict[str, Any]) -> str:
    return json.dumps(event) + "\n"

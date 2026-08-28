from __future__ import annotations

from time import perf_counter
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from models.model_client import ModelCallError, ModelClient, get_model_client
from utils.app_logger import get_logger

router = APIRouter(prefix="/api", tags=["health"])
logger = get_logger("api.health")


class LLMProbeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok"]


class DependencyHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["up", "down"]
    model: str
    latency_ms: float = Field(ge=0.0)


class ReadinessHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ready", "not_ready"]
    checks: dict[str, DependencyHealth]


def get_health_model_client() -> ModelClient:
    return get_model_client()


HealthModelClient = Annotated[ModelClient, Depends(get_health_model_client)]


@router.get("/health")
def health() -> dict[str, str]:
    """Cheap liveness probe: the API process can accept and route requests."""
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(model_client: HealthModelClient) -> JSONResponse:
    try:
        result = model_client.json_response(
            system="Return JSON.",
            prompt='Return {"status": "ok"}.',
            fallback={},
            timeout_seconds=10,
            max_output_tokens=128,
        )
        if not result.used_model:
            raise ModelCallError("LLM readiness probe did not execute a model call.")
        return JSONResponse(status_code=200, content={"status": "ready"})
    except ModelCallError:
        logger.exception("LLM readiness check failed.")
        return JSONResponse(status_code=503, content={"status": "not_ready"})

def _elapsed_ms(started_at: float) -> float:
    return round(max(0.0, perf_counter() - started_at) * 1_000, 2)

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.claim_request_api import router as claim_request_router
from api.health_api import router as health_router
from models.model_client import ModelCallError
from security.api_protection import ApiProtector

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

_rate_limit = max(1, int(os.getenv("APP_RATE_LIMIT_PER_MINUTE", "60")))
protect_api = ApiProtector(api_key=os.getenv("APP_API_KEY"), requests_per_minute=_rate_limit)
app.middleware("http")(protect_api)


@app.exception_handler(ModelCallError)
async def model_call_error_handler(_, exc: ModelCallError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Model-backed agents are required, but a model call failed.",
            "error": str(exc),
            "hint": "Check backend/config/config.*.json, APP_ENV, OPENAI_API_KEY, selected OpenAI model names, billing, and model access.",
        },
    )


app.include_router(claim_request_router)
app.include_router(health_router)

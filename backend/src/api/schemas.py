from pydantic import BaseModel, Field


class ModelTestRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    system: str | None = None
    model: str | None = None


class ModelTestResponse(BaseModel):
    provider: str
    model: str
    used_model: bool
    answer: str

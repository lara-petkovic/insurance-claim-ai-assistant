from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from pydantic import Field

from models.model_client import ModelCallError, ModelClient


class StructuredDecision(BaseModel):
    decision: str
    score: float


class BoundedDecision(BaseModel):
    decision: str
    score: float = Field(ge=0.0, le=1.0)


class FakeResponses:
    def __init__(self, output_text: str):
        self.output_text = output_text
        self.last_create_kwargs = None

    def create(self, **kwargs):
        self.last_create_kwargs = kwargs
        return SimpleNamespace(output_text=self.output_text)


class FakeOpenAI:
    def __init__(self, output_text: str):
        self.responses = FakeResponses(output_text)


def make_client(output_text: str) -> ModelClient:
    client = ModelClient.__new__(ModelClient)
    client.api_key = "test-key"
    client.text_model = "text-test-model"
    client.planning_model = "planning-test-model"
    client.vision_model = "vision-test-model"
    client._client = FakeOpenAI(output_text)
    client.init_error = None
    return client


def test_json_response_uses_structured_output_with_pydantic_model():
    client = make_client('{"decision": "covered", "score": 0.91}')

    result = client.json_response(
        system="Return a decision.",
        prompt="Claim facts.",
        fallback={"decision": "fallback", "score": 0.0},
        response_model=StructuredDecision,
        schema_name="coverage_decision",
    )

    assert result.data == {"decision": "covered", "score": 0.91}
    assert result.used_model is True
    request = client._client.responses.last_create_kwargs
    assert request["model"] == "text-test-model"
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["text"]["format"]["name"] == "coverage_decision"
    assert request["text"]["format"]["strict"] is True
    assert "schema" in request["text"]["format"]


def test_json_response_raises_for_invalid_legacy_json_without_schema():
    client = make_client("not JSON at all")

    with pytest.raises(ModelCallError, match="OpenAI model returned invalid JSON"):
        client.json_response(
            system="Return JSON.",
            prompt="Claim facts.",
            fallback={"decision": "fallback"},
        )
    assert "text" not in client._client.responses.last_create_kwargs


def test_image_json_response_supports_image_input_and_structured_output():
    client = make_client('{"decision": "visible", "score": 0.8}')

    result = client.image_json_response(
        system="Inspect image.",
        prompt="Classify damage.",
        image_bytes=b"fake-image",
        image_mime_type="image/png",
        fallback={"decision": "fallback", "score": 0.0},
        response_model=StructuredDecision,
    )

    assert result.data == {"decision": "visible", "score": 0.8}
    request = client._client.responses.last_create_kwargs
    assert request["model"] == "vision-test-model"
    assert request["text"]["format"]["type"] == "json_schema"
    user_content = request["input"][1]["content"]
    assert user_content[0] == {"type": "input_text", "text": "Classify damage."}
    assert user_content[1]["type"] == "input_image"
    assert user_content[1]["image_url"].startswith("data:image/png;base64,")


def test_file_json_response_supports_pdf_input_and_structured_output():
    client = make_client('{"decision": "extracted", "score": 1.0}')

    result = client.file_json_response(
        system="Extract file text.",
        prompt="Read this PDF.",
        file_bytes=b"%PDF-fake",
        file_mime_type="application/pdf",
        filename="policy.pdf",
        fallback={"decision": "fallback", "score": 0.0},
        response_model=StructuredDecision,
    )

    assert result.data == {"decision": "extracted", "score": 1.0}
    request = client._client.responses.last_create_kwargs
    assert request["model"] == "vision-test-model"
    assert request["text"]["format"]["type"] == "json_schema"
    user_content = request["input"][1]["content"]
    assert user_content[0] == {"type": "input_text", "text": "Read this PDF."}
    assert user_content[1]["type"] == "input_file"
    assert user_content[1]["filename"] == "policy.pdf"
    assert user_content[1]["file_data"].startswith("data:application/pdf;base64,")


def test_model_json_failure_is_always_fatal():
    client = make_client("not JSON")

    with pytest.raises(ModelCallError, match="OpenAI model returned invalid JSON"):
        client.json_response(
            system="Return JSON.",
            prompt="Claim facts.",
            fallback={"decision": "fallback"},
        )


def test_malformed_structured_model_output_fails_validation():
    client = make_client('{"decision": "covered", "score": 1.5}')

    with pytest.raises(ModelCallError, match="validation error"):
        client.json_response(
            system="Return a bounded decision.",
            prompt="Claim facts.",
            fallback={"decision": "fallback", "score": 0.0},
            response_model=BoundedDecision,
        )

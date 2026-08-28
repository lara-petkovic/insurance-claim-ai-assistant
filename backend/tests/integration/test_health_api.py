from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api import health_api
from main import app
from models.model_client import ModelCallError, ModelResult


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


class HealthyModelClient:
    text_model = "health-test-model"

    def json_response(self, **kwargs):
        assert kwargs["timeout_seconds"] == 10
        assert kwargs["max_output_tokens"] == 128
        return ModelResult(data={"status": "ok"}, used_model=True)


def test_liveness_does_not_call_external_dependencies():
    app.dependency_overrides[health_api.get_health_model_client] = lambda: SimpleNamespace(
        text_model="must-not-run",
        json_response=lambda **_: pytest.fail("Liveness must not call the LLM."),
    )

    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_performs_real_llm_probe_contract():
    app.dependency_overrides[health_api.get_health_model_client] = HealthyModelClient

    response = TestClient(app).get("/api/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_returns_sanitized_503_when_llm_is_unavailable():
    class UnhealthyModelClient:
        text_model = "health-test-model"

        def json_response(self, **_):
            raise ModelCallError("secret provider or account detail")

    app.dependency_overrides[health_api.get_health_model_client] = UnhealthyModelClient

    response = TestClient(app).get("/api/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert "secret provider or account detail" not in response.text


def test_readiness_rejects_a_fallback_without_a_model_call():
    class FallbackModelClient:
        text_model = "health-test-model"

        def json_response(self, **_):
            return ModelResult(data={"status": "ok"}, used_model=False)

    app.dependency_overrides[health_api.get_health_model_client] = FallbackModelClient

    response = TestClient(app).get("/api/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}

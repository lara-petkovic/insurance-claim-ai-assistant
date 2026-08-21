import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api import claim_request_api
from main import app
from services import claim_request_builder


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def test_health_endpoint():
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_stream_endpoint_accepts_frontend_form_contract():
    captured = {}

    def fake_stream(request):
        captured["request"] = request
        yield {"event": "analysis_started", "total_agents": 1}
        yield {"event": "analysis_completed", "result": {"claim_status": "requires_human_review"}}

    app.dependency_overrides[claim_request_api.get_orchestrator] = lambda: SimpleNamespace(
        stream=fake_stream
    )

    response = TestClient(app).post(
        "/api/claims/analyze-stream",
        data={
            "insurance_type": "home",
            "claim_description": "A pipe burst in the bathroom.",
            "incident_date": "2026-06-25",
        },
        files={
            "policy_file": ("policy.txt", b"Escape of water is covered.", "text/plain"),
            "damage_image": ("damage.jpg", b"image-bytes", "image/jpeg"),
            "supporting_documents": ("plumber-report.txt", b"report", "text/plain"),
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines() if line]
    assert [event["event"] for event in events] == [
        "analysis_started",
        "analysis_completed",
    ]

    request = captured["request"]
    assert request.insurance_type == "home"
    assert request.claim_description == "A pipe burst in the bathroom."
    assert request.incident_date == "2026-06-25"
    assert request.policy_filename == "policy.txt"
    assert request.damage_image_filename == "damage.jpg"
    assert request.supporting_document_names == ["plumber-report.txt"]
    assert request.supporting_documents[0].text == "report"
    assert request.supporting_documents[0].text_length == 6


def test_supporting_documents_are_extracted_independently_and_warnings_are_preserved(monkeypatch):
    captured = {}

    async def fake_extract(filename, content):
        if filename == "broken.pdf":
            raise ValueError("unreadable upload")
        return content.decode(), (["partial extraction"] if filename == "estimate.txt" else [])

    def fake_analyze(request):
        captured["request"] = request
        from core.models.claim import ClaimAnalysisResult
        return ClaimAnalysisResult(
            claim_status="requires_human_review", insurance_type="home", claim_type="water_damage",
            coverage_assessment="unclear", reasoning_summary="Review required.", recommendation="Review."
        )

    monkeypatch.setattr(claim_request_builder, "extract_upload_text", fake_extract)
    app.dependency_overrides[claim_request_api.get_orchestrator] = lambda: SimpleNamespace(
        analyze=fake_analyze
    )
    response = TestClient(app).post(
        "/api/claims/analyze",
        data={"claim_description": "Water damage"},
        files=[
            ("policy_file", ("policy.txt", b"Water damage is covered", "text/plain")),
            ("supporting_documents", ("estimate.txt", b"Repair estimate: 500", "text/plain")),
            ("supporting_documents", ("broken.pdf", b"bad", "application/pdf")),
            ("supporting_documents", ("receipt.txt", b"Receipt paid", "text/plain")),
        ],
    )

    assert response.status_code == 200
    documents = captured["request"].supporting_documents
    assert [document.filename for document in documents] == ["estimate.txt", "broken.pdf", "receipt.txt"]
    assert documents[0].extraction_warnings == ["partial extraction"]
    assert documents[1].text == ""
    assert "unreadable upload" in documents[1].extraction_warnings[0]
    assert documents[2].text == "Receipt paid"


def test_oversized_supporting_document_is_not_downgraded_to_warning(monkeypatch):
    monkeypatch.setattr(claim_request_builder, "MAX_SUPPORTING_FILE_BYTES", 3)

    response = TestClient(app).post(
        "/api/claims/analyze",
        data={"claim_description": "Water damage"},
        files=[
            ("policy_file", ("policy.txt", b"Water damage is covered", "text/plain")),
            ("supporting_documents", ("receipt.txt", b"four", "text/plain")),
        ],
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Uploaded file exceeds the 0 MB limit."}


def test_stream_failure_does_not_expose_internal_error():
    def fake_stream(_):
        raise RuntimeError("secret provider detail")
        yield

    app.dependency_overrides[claim_request_api.get_orchestrator] = lambda: SimpleNamespace(
        stream=fake_stream
    )

    response = TestClient(app).post(
        "/api/claims/analyze-stream",
        data={"claim_description": "Water damage"},
        files={"policy_file": ("policy.txt", b"Water damage is covered", "text/plain")},
    )

    assert response.status_code == 200
    event = json.loads(response.text)
    assert event == {
        "event": "analysis_failed",
        "error": "Claim analysis failed. Please retry or request human review.",
    }
    assert "secret provider detail" not in response.text

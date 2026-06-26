import json

from fastapi.testclient import TestClient

from main import app
from api import routes_api


def test_health_endpoint():
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_stream_endpoint_accepts_frontend_form_contract(monkeypatch):
    captured = {}

    def fake_stream(request):
        captured["request"] = request
        yield {"event": "analysis_started", "total_agents": 1}
        yield {"event": "analysis_completed", "result": {"claim_status": "requires_human_review"}}

    monkeypatch.setattr(routes_api.orchestrator, "stream", fake_stream)

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

import asyncio

from data import text_extraction
from models.model_client import ModelResult


def test_pdf_with_no_pypdf_text_uses_model_fallback(monkeypatch):
    class FakeModelClient:
        def file_json_response(self, **kwargs):
            assert kwargs["file_mime_type"] == "application/pdf"
            assert kwargs["schema_name"] == "pdf_policy_text_extraction"
            return ModelResult(
                data={
                    "text": "Scanned policy wording extracted by vision. Covered events and exclusions.",
                    "warnings": ["Some small table text may require manual review."],
                },
                used_model=True,
            )

    monkeypatch.setattr(text_extraction, "get_model_client", lambda: FakeModelClient())

    text, warnings = asyncio.run(text_extraction.extract_upload_text("policy.pdf", b"not a real pdf"))

    assert "Scanned policy wording extracted by vision" in text
    assert any("vision extraction fallback was attempted" in warning for warning in warnings)
    assert "Used vision extraction fallback because PDF text extraction was insufficient." in warnings
    assert "Some small table text may require manual review." in warnings


def test_pdf_fallback_preserves_short_pypdf_text_when_model_unavailable(monkeypatch):
    class FakeModelClient:
        def file_json_response(self, **kwargs):
            return ModelResult(
                data={"text": kwargs["fallback"]["text"], "warnings": []},
                used_model=False,
                error="Model client is unavailable.",
            )

    class FakePage:
        def extract_text(self):
            return "Short policy text."

    class FakePdfReader:
        def __init__(self, _):
            self.pages = [FakePage()]

    monkeypatch.setattr(text_extraction, "get_model_client", lambda: FakeModelClient())
    monkeypatch.setattr("pypdf.PdfReader", FakePdfReader)

    text, warnings = asyncio.run(text_extraction.extract_upload_text("policy.pdf", b"%PDF fake"))

    assert text == "Short policy text."
    assert any("only 18 characters" in warning for warning in warnings)
    assert "Model client is unavailable." in warnings

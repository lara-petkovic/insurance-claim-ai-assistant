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


def test_pdf_extraction_preserves_page_boundaries_and_offsets(monkeypatch):
    class FakePage:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    first = ("PAGE ONE\n" + ("coverage wording " * 20)).strip()
    second = ("PAGE TWO\n" + ("exclusion wording " * 20)).strip()

    class FakePdfReader:
        def __init__(self, _):
            self.pages = [FakePage(first), FakePage(second)]

    monkeypatch.setattr("pypdf.PdfReader", FakePdfReader)

    document = asyncio.run(text_extraction.extract_upload_document("policy.pdf", b"%PDF fake"))

    assert document.text == f"{first}\n\n{second}"
    assert [page.page_number for page in document.pages] == [1, 2]
    assert document.pages[0].char_start == 0
    assert document.pages[0].char_end == len(first)
    assert document.pages[1].char_start == len(first) + 2
    assert document.text[document.pages[1].char_start : document.pages[1].char_end] == second

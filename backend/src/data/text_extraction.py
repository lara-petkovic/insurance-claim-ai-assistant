from __future__ import annotations

from pathlib import Path
from typing import Any

from models.model_client import get_model_client

MIN_USEFUL_PDF_TEXT_CHARS = 500
PDF_TEXT_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "text": {"type": "string"},
        "warnings": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 8,
        },
    },
    "required": ["text", "warnings"],
}


async def extract_upload_text(filename: str, content: bytes) -> tuple[str, list[str]]:
    """Extract text from a small uploaded file using replaceable MVP logic."""
    warnings: list[str] = []
    suffix = Path(filename).suffix.lower()

    if suffix in {".txt", ".md", ".json", ".csv"}:
        return content.decode("utf-8", errors="ignore"), warnings

    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            from io import BytesIO

            reader = PdfReader(BytesIO(content))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n\n".join(pages).strip()
        except Exception as exc:
            warnings.append(f"PDF extraction failed: {exc}")
            text = ""

        if len(text) >= MIN_USEFUL_PDF_TEXT_CHARS:
            return text, warnings
        if text:
            warnings.append(
                f"PDF text extraction returned only {len(text)} characters, so vision extraction fallback was attempted."
            )
        else:
            warnings.append("PDF text extraction returned no text, so vision extraction fallback was attempted.")
        fallback_text, fallback_warnings = _extract_pdf_with_model(
            filename=filename,
            content=content,
            existing_text=text,
        )
        warnings.extend(fallback_warnings)
        return (fallback_text or text).strip(), warnings

    warnings.append(f"Unsupported text extraction for file type '{suffix}'.")
    return "", warnings


def _extract_pdf_with_model(*, filename: str, content: bytes, existing_text: str) -> tuple[str, list[str]]:
    fallback = {"text": existing_text, "warnings": []}
    model_result = get_model_client().file_json_response(
        system=(
            "You extract readable text from insurance policy PDFs. "
            "Return only valid JSON matching the schema. Preserve headings, clauses, tables, exclusions, limits, and conditions."
        ),
        prompt=(
            "Extract the policy wording from this PDF. If the PDF is scanned, image-based, or mixed-language, "
            "read it visually. Keep English text as written. Return a single text field with useful "
            "line breaks and a warnings array describing extraction limitations."
        ),
        file_bytes=content,
        file_mime_type="application/pdf",
        filename=filename or "policy.pdf",
        fallback=fallback,
        schema_name="pdf_policy_text_extraction",
        json_schema=PDF_TEXT_EXTRACTION_SCHEMA,
        schema_description="Extracted insurance policy text and extraction warnings.",
    )
    if not model_result.used_model:
        return existing_text, [model_result.error or "Vision extraction fallback was unavailable."]

    extracted_text = str(model_result.data.get("text", "")).strip()
    model_warnings = [str(item) for item in model_result.data.get("warnings", []) if str(item).strip()]
    if extracted_text:
        return extracted_text, ["Used vision extraction fallback because PDF text extraction was insufficient.", *model_warnings]
    return existing_text, ["Vision extraction fallback returned no usable text.", *model_warnings]


def infer_document_type(filename: str) -> str:
    name = filename.lower()
    if any(token in name for token in ["policy", "wording", "insurance"]):
        return "policy"
    if any(token in name for token in ["invoice", "estimate", "receipt"]):
        return "financial_support"
    if any(token in name for token in ["police", "report"]):
        return "report"
    if any(token in name for token in ["jpg", "jpeg", "png", "webp", "image", "photo"]):
        return "image"
    return "supporting_document"

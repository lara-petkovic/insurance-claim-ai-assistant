from __future__ import annotations

from pathlib import Path


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
            if text:
                return text, warnings
            warnings.append("PDF text extraction returned no text. OCR service can be plugged in later.")
            return "", warnings
        except Exception as exc:  # pragma: no cover - depends on optional parser/runtime
            warnings.append(f"PDF extraction failed: {exc}")
            return "", warnings

    warnings.append(f"Unsupported text extraction for file type '{suffix}'.")
    return "", warnings


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

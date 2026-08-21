"""Build validated domain requests from uploaded claim form data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile

from core.models.analysis import DocumentPage, PolicyDocument, SourceDocument
from core.models.claim import ClaimRequestData, InsuranceType, SupportingDocumentData
from data.text_extraction import extract_upload_text, infer_document_type
from security.input_security import (
    ALLOWED_IMAGE_MIME_TYPES,
    ALLOWED_POLICY_SUFFIXES,
    ALLOWED_SUPPORTING_SUFFIXES,
    MAX_CLAIM_DESCRIPTION_CHARS,
    MAX_EXTRACTED_TEXT_CHARS,
    MAX_IMAGE_BYTES,
    MAX_POLICY_BYTES,
    MAX_SUPPORTING_DOCUMENTS,
    MAX_SUPPORTING_FILE_BYTES,
    detect_prompt_injection,
)


@dataclass(frozen=True)
class _ImageData:
    filename: str | None = None
    size: int | None = None
    mime_type: str | None = None
    content: bytes | None = None


async def build_claim_request(
    insurance_type: InsuranceType | str,
    claim_description: str,
    incident_date: str | None,
    policy_file: UploadFile | None,
    damage_image: UploadFile | None,
    supporting_documents: list[UploadFile] | None,
) -> ClaimRequestData:
    _validate_form_limits(claim_description, supporting_documents)
    security_flags = [f"claim_description:{flag}" for flag in detect_prompt_injection(claim_description)]
    policy_text, policy_filename, policy_warnings, policy_document = await _process_policy(
        policy_file, security_flags
    )
    image_data = await _process_damage_image(damage_image)
    documents = await _process_supporting_documents(supporting_documents, security_flags)

    return ClaimRequestData(
        insurance_type=insurance_type,
        claim_description=claim_description,
        incident_date=incident_date,
        policy_text=policy_text,
        policy_filename=policy_filename,
        policy_extraction_warnings=policy_warnings,
        policy_document=policy_document,
        damage_image_filename=image_data.filename,
        damage_image_size=image_data.size,
        damage_image_mime_type=image_data.mime_type,
        damage_image_bytes=image_data.content,
        supporting_documents=documents,
        security_flags=sorted(set(security_flags)),
    )


async def read_bounded_upload(file: UploadFile, limit: int) -> bytes:
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(
            status_code=413,
            detail=f"Uploaded file exceeds the {limit // (1024 * 1024)} MB limit.",
        )
    return content


def validate_upload_suffix(filename: str, allowed: set[str]) -> None:
    if Path(filename).suffix.lower() not in allowed:
        raise HTTPException(status_code=415, detail="Unsupported file type.")


def _validate_form_limits(
    claim_description: str,
    supporting_documents: list[UploadFile] | None,
) -> None:
    if len(claim_description) > MAX_CLAIM_DESCRIPTION_CHARS:
        raise HTTPException(status_code=413, detail="Claim description is too large.")
    if len(supporting_documents or []) > MAX_SUPPORTING_DOCUMENTS:
        raise HTTPException(
            status_code=413,
            detail=f"At most {MAX_SUPPORTING_DOCUMENTS} supporting documents are allowed.",
        )


async def _process_policy(
    policy_file: UploadFile | None,
    security_flags: list[str],
) -> tuple[str, str | None, list[str], PolicyDocument]:
    if policy_file is None:
        raise _missing_policy_error()

    filename = policy_file.filename or "policy.pdf"
    validate_upload_suffix(filename, ALLOWED_POLICY_SUFFIXES)
    content = await read_bounded_upload(policy_file, MAX_POLICY_BYTES)
    extraction = await extract_upload_text(filename, content)
    policy_text, warnings = extraction
    policy_text = policy_text[:MAX_EXTRACTED_TEXT_CHARS]
    security_flags.extend(
        f"policy:{flag}" for flag in detect_prompt_injection(policy_text)
    )
    if not policy_text.strip():
        raise _missing_policy_error()
    extracted_document = getattr(extraction, "document", None)
    policy_document = PolicyDocument(
        document_id=getattr(extracted_document, "document_id", ""),
        filename=filename,
        text=policy_text,
        pages=_bounded_pages(extracted_document, policy_text),
        extraction_method=getattr(extracted_document, "extraction_method", "text_extraction"),
        extraction_warnings=warnings,
    )
    return policy_text, policy_file.filename, warnings, policy_document


async def _process_damage_image(damage_image: UploadFile | None) -> _ImageData:
    if damage_image is None:
        return _ImageData()
    if damage_image.content_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported damage image type.")
    content = await read_bounded_upload(damage_image, MAX_IMAGE_BYTES)
    return _ImageData(
        filename=damage_image.filename,
        size=len(content),
        mime_type=damage_image.content_type,
        content=content,
    )


async def _process_supporting_documents(
    supporting_documents: list[UploadFile] | None,
    security_flags: list[str],
) -> list[SupportingDocumentData]:
    results: list[SupportingDocumentData] = []
    for document in supporting_documents or []:
        filename = document.filename or "supporting_document"
        validate_upload_suffix(filename, ALLOWED_SUPPORTING_SUFFIXES)
        content = await read_bounded_upload(document, MAX_SUPPORTING_FILE_BYTES)
        text, warnings, extracted_document = await _extract_supporting_text(filename, content)
        text = text[:MAX_EXTRACTED_TEXT_CHARS]
        security_flags.extend(
            f"supporting_document:{flag}" for flag in detect_prompt_injection(text)
        )
        if not text.strip() and not warnings:
            warnings.append("Supporting document extraction returned no usable text.")
        results.append(
            SupportingDocumentData(
                document_id=getattr(extracted_document, "document_id", ""),
                filename=filename,
                document_type=infer_document_type(filename),
                text=text,
                pages=_bounded_pages(extracted_document, text),
                extraction_method=getattr(extracted_document, "extraction_method", "text_extraction"),
                extraction_warnings=warnings,
                text_length=len(text),
            )
        )
    return results


async def _extract_supporting_text(
    filename: str,
    content: bytes,
) -> tuple[str, list[str], SourceDocument | None]:
    try:
        extraction = await extract_upload_text(filename, content)
        text, warnings = extraction
        document = getattr(extraction, "document", None)
        return text, warnings, document if isinstance(document, SourceDocument) else None
    except Exception as exc:
        return "", [f"Supporting document extraction failed: {exc}"], None


def _missing_policy_error() -> HTTPException:
    return HTTPException(
        status_code=400,
        detail=(
            "Policy text is required. Upload a PDF or text policy document that can "
            "be extracted by text or vision fallback."
        ),
    )


def _bounded_pages(document: SourceDocument | None, bounded_text: str) -> list[DocumentPage]:
    """Crop page spans when the security text limit truncates an extracted document."""
    if document is None:
        return []
    pages = []
    for page in document.pages:
        if page.char_start >= len(bounded_text):
            continue
        char_end = min(page.char_end, len(bounded_text))
        page_text = bounded_text[page.char_start:char_end]
        pages.append(
            DocumentPage(
                page_number=page.page_number,
                text=page_text,
                char_start=page.char_start,
                char_end=char_end,
                extraction_method=page.extraction_method,
            )
        )
    return pages

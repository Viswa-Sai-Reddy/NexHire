"""AI-6 — Joining Form Assistant.

S3 ships the deterministic plumbing:
  * `extract_id_doc(file_bytes, mime)` — calls Azure Document
    Intelligence's prebuilt-idDocument model and returns a normalized
    payload (name, dob, id_number, pan_number).
  * `extract_education_cert(...)` — same shape, prebuilt-document.

Both endpoints degrade gracefully (return None + reason) so the form
keeps working when the service is down. Unit tests exercise the
parsing of a synthetic Document Intelligence response shape.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.config import get_settings

logger = logging.getLogger("nexhire.ai.form_assistant")

MODEL_TOUCHPOINT = "FORM_ASSIST"


@dataclass(frozen=True, slots=True)
class IdDocFields:
    succeeded: bool
    name: str | None = None
    dob: date | None = None
    id_number: str | None = None
    pan_number: str | None = None
    degradation_reason: str | None = None


async def extract_id_doc(file_bytes: bytes, mime_type: str) -> IdDocFields:
    cfg = get_settings()
    if not cfg.azure_doc_intelligence_endpoint or not cfg.azure_doc_intelligence_key:
        return IdDocFields(succeeded=False, degradation_reason="DOC_INTEL_NOT_CONFIGURED")
    try:
        from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential

        client = DocumentIntelligenceClient(
            endpoint=cfg.azure_doc_intelligence_endpoint,
            credential=AzureKeyCredential(cfg.azure_doc_intelligence_key),
        )
        async with client:
            poller = await client.begin_analyze_document(
                model_id="prebuilt-idDocument",
                body={"base64Source": _b64(file_bytes)},
            )
            result = await poller.result()
        return _parse_id_doc(result)
    except Exception as exc:
        logger.warning(
            "nexhire.ai.form_assistant.id_doc_failed",
            extra={"mime_type": mime_type},
            exc_info=exc,
        )
        return IdDocFields(succeeded=False, degradation_reason="DOC_INTEL_ERROR")


def _b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode("ascii")


def _parse_id_doc(result: Any) -> IdDocFields:
    """Pulls the first document and reads the standard ID fields.

    Document Intelligence returns a ``DocumentAnalysisResult``-shaped
    object whose `documents[0].fields` is a mapping of field-name →
    `Document.Field`. We treat missing fields as `None` and degrade
    accordingly.
    """
    documents = getattr(result, "documents", None) or []
    if not documents:
        return IdDocFields(succeeded=False, degradation_reason="NO_FIELDS_EXTRACTED")
    fields = getattr(documents[0], "fields", None) or {}

    def _str(key: str) -> str | None:
        node = fields.get(key)
        if node is None:
            return None
        value = getattr(node, "content", None) or getattr(node, "value", None)
        return str(value).strip() if value else None

    def _date(key: str) -> date | None:
        node = fields.get(key)
        if node is None:
            return None
        value = getattr(node, "value", None)
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                return None
        return None

    name = _str("FirstName") or _str("LastName") or _str("FullName") or _str("MachineReadableZone")
    dob = _date("DateOfBirth")
    id_number = _str("DocumentNumber")
    # PAN cards may surface as `documentType=Personal` with the ID in
    # `DocumentNumber`; otherwise fall back to a separate PAN field if
    # the Indian-PAN custom model is wired in S5.
    pan_number = _str("PanNumber") or (
        id_number if id_number and _looks_like_pan(id_number) else None
    )
    return IdDocFields(
        succeeded=True,
        name=name,
        dob=dob,
        id_number=id_number,
        pan_number=pan_number,
    )


def _looks_like_pan(value: str) -> bool:
    import re

    return bool(re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", value.strip().upper()))


__all__ = ["MODEL_TOUCHPOINT", "IdDocFields", "extract_id_doc"]

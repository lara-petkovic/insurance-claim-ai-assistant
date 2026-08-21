"""Deterministic insurance-domain and date validation helpers."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from core.models.claim import InsuranceType

DATE_TOKEN_PATTERN = r"(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{4})"
_DATE_TOKEN_RE = re.compile(rf"\b({DATE_TOKEN_PATTERN})\b")
_POLICY_PERIOD_RE = re.compile(
    rf"(?:policy\s+period|period\s+of\s+(?:insurance|cover)|coverage|cover|effective)"
    rf"[^\n]{{0,80}}?({DATE_TOKEN_PATTERN})"
    rf"\s*(?:to|until|through|thru|-)\s*({DATE_TOKEN_PATTERN})",
    re.IGNORECASE,
)

INSURED_SUBJECT_TYPES = {
    InsuranceType.HOME: "residential_property",
    InsuranceType.AUTO: "insured_vehicle",
    InsuranceType.TRAVEL: "insured_person_or_trip",
}

CLAIM_SUBJECT_DOMAINS = {
    "water_damage": InsuranceType.HOME,
    "storm_damage": InsuranceType.HOME,
    "fire_damage": InsuranceType.HOME,
    "broken_glass": InsuranceType.HOME,
    "vehicle_damage": InsuranceType.AUTO,
    "medical": InsuranceType.TRAVEL,
    "baggage_loss": InsuranceType.TRAVEL,
    "trip_cancellation": InsuranceType.TRAVEL,
}


def parse_date_value(value: object) -> tuple[date | None, str]:
    """Parse supported user/policy date formats without model involvement."""
    if value is None or not str(value).strip():
        return None, "missing"
    raw = str(value).strip()
    for date_format in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, date_format).date(), "valid"
        except ValueError:
            continue
    return None, "invalid"


def extract_policy_period(policy_text: str) -> dict[str, Any]:
    """Return typed policy dates plus a stable validation status."""
    pair_match = _POLICY_PERIOD_RE.search(policy_text)
    raw_dates = list(pair_match.groups()) if pair_match else _DATE_TOKEN_RE.findall(policy_text)
    if not raw_dates:
        return {
            "start": None,
            "end": None,
            "status": "missing",
            "raw_start": None,
            "raw_end": None,
        }

    raw_start = raw_dates[0]
    raw_end = raw_dates[1] if len(raw_dates) > 1 else None
    start, start_status = parse_date_value(raw_start)
    end, end_status = parse_date_value(raw_end)
    if start_status == "invalid" or end_status == "invalid":
        status = "invalid"
    elif start is None or end is None:
        status = "unverifiable"
    elif start > end:
        status = "invalid"
    else:
        status = "valid"
    return {
        "start": start,
        "end": end,
        "status": status,
        "raw_start": raw_start,
        "raw_end": raw_end,
    }


def policy_domain_metadata(insurance_type: InsuranceType, policy_text: str) -> dict[str, Any]:
    """Build deterministic policy type and subject metadata for the selected domain."""
    return {
        "policy_type": f"{insurance_type.value}_insurance",
        "insured_subject": {
            "type": INSURED_SUBJECT_TYPES[insurance_type],
            "domain": insurance_type.value,
            "source": "policy",
            "identifiers": extract_subject_identifiers(policy_text, insurance_type),
        },
    }


def extract_subject_identifiers(text: str, insurance_type: InsuranceType) -> dict[str, str]:
    """Extract identifiers only when both policy and claim can be compared reliably."""
    patterns: dict[str, str]
    if insurance_type is InsuranceType.AUTO:
        patterns = {
            "vin": r"\b(?:VIN|vehicle identification number)\s*[:#-]?\s*([A-HJ-NPR-Z0-9]{11,17})\b",
            "registration": r"\b(?:registration|reg(?:istration)? no\.?|licen[cs]e plate|number plate)\s*[:#-]?\s*([A-Z0-9-]{3,12})\b",
        }
    elif insurance_type is InsuranceType.HOME:
        patterns = {
            "property_address": r"\b(?:insured property|property address|risk address)\s*:\s*([^\n.;]+)",
        }
    else:
        patterns = {
            "booking_reference": r"\b(?:booking|trip|reservation)\s+(?:reference|number)\s*[:#-]?\s*([A-Z0-9-]{3,20})\b",
        }

    identifiers = {}
    for name, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            identifiers[name] = _normalize_identifier(match.group(1))
    return identifiers


def inferred_claim_subject_domain(claim_type: object) -> InsuranceType | None:
    return CLAIM_SUBJECT_DOMAINS.get(str(claim_type))


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())

"""Strict output schemas shared by model-backed agents."""

COVERAGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "coverage_assessment": {
            "type": "string",
            "enum": ["covered", "not_covered", "possibly_covered", "unclear"],
        },
        "matched_policy_concepts": {
            "type": "array",
            "maxItems": 20,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "concept": {"type": "string", "maxLength": 100},
                    "evidence_text": {"type": "string", "maxLength": 2_000},
                },
                "required": ["concept", "evidence_text"],
            },
        },
        "explanation": {"type": "string", "maxLength": 4_000},
        "suspected_prompt_injection": {"type": "boolean"},
    },
    "required": [
        "coverage_assessment",
        "matched_policy_concepts",
        "explanation",
        "suspected_prompt_injection",
    ],
}

EXCLUSION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "potential_exclusions": {
            "type": "array",
            "maxItems": 20,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "concept": {"type": "string", "maxLength": 100},
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "reason": {"type": "string", "maxLength": 2_000},
                    "evidence_text": {"type": "string", "maxLength": 2_000},
                },
                "required": ["concept", "severity", "reason", "evidence_text"],
            },
        },
        "suspected_prompt_injection": {"type": "boolean"},
    },
    "required": ["potential_exclusions", "suspected_prompt_injection"],
}

__all__ = ["COVERAGE_SCHEMA", "EXCLUSION_SCHEMA"]

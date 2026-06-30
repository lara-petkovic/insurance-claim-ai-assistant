from typing import TypedDict


class ClaimThemeConfig(TypedDict):
    keywords: list[str]
    evidence_focus: list[str]
    fallback_rationale: str
    theme_rationale: str


class FunctionalChecklistItem(TypedDict):
    check: str
    target_agent: str


CLAIM_THEME_CONFIG: dict[str, ClaimThemeConfig] = {
    "theft": {
        "keywords": ["stolen", "theft", "burglar", "broke into", "taken", "missing items", "forced entry"],
        "evidence_focus": ["police report", "proof of ownership", "forcible entry evidence"],
        "fallback_rationale": "The claim text suggests theft, so evidence planning emphasizes police report and ownership checks.",
        "theme_rationale": "The claim appears theft-related, so evidence planning emphasizes police report and ownership checks.",
    },
    "storm_damage": {
        "keywords": ["storm", "roof", "hail", "wind", "heavy rain", "tiles", "weather damage"],
        "evidence_focus": ["weather evidence", "damage photos", "repair estimate"],
        "fallback_rationale": "The claim text suggests storm damage, so planning emphasizes weather evidence and wear-and-tear exclusions.",
        "theme_rationale": "The claim appears storm-related, so planning emphasizes weather evidence and wear-and-tear exclusions.",
    },
    "water_damage": {
        "keywords": ["leak", "water", "pipe", "ceiling", "flood", "moisture", "burst", "escape of water"],
        "evidence_focus": ["plumber report", "repair estimate", "damage photos"],
        "fallback_rationale": "The claim text suggests water damage, so planning emphasizes sudden escape of water, gradual damage exclusions, and plumber evidence.",
        "theme_rationale": "The claim appears water damage related, so planning emphasizes sudden escape of water, gradual damage exclusions, and plumber evidence.",
    },
    "fire_damage": {
        "keywords": ["fire", "smoke", "burn", "explosion"],
        "evidence_focus": ["incident report", "damage photos", "repair estimate"],
        "fallback_rationale": "The claim text suggests fire damage, so planning emphasizes incident evidence and repair scope.",
        "theme_rationale": "The claim appears fire-related, so planning emphasizes incident evidence and repair scope.",
    },
    "vehicle_damage": {
        "keywords": ["car", "vehicle", "collision", "crash", "accident", "bumper"],
        "evidence_focus": ["damage photos", "repair estimate", "vehicle details"],
        "fallback_rationale": "The claim text suggests vehicle damage, so planning emphasizes repair estimates and damage evidence.",
        "theme_rationale": "The claim appears vehicle-damage related, so planning emphasizes repair estimates and damage evidence.",
    },
    "medical": {
        "keywords": ["doctor", "hospital", "medical", "illness", "injury", "ambulance"],
        "evidence_focus": ["medical report", "medical receipts", "incident date"],
        "fallback_rationale": "The claim text suggests a medical claim, so planning emphasizes treatment evidence and receipts.",
        "theme_rationale": "The claim appears medical, so planning emphasizes treatment evidence and receipts.",
    },
    "baggage_loss": {
        "keywords": ["baggage", "luggage", "suitcase", "lost bag", "airline lost", "airport"],
        "evidence_focus": ["carrier report", "proof of ownership", "travel documents"],
        "fallback_rationale": "The claim text suggests baggage loss, so planning emphasizes carrier reports and ownership evidence.",
        "theme_rationale": "The claim appears baggage-loss related, so planning emphasizes carrier reports and ownership evidence.",
    },
    "trip_cancellation": {
        "keywords": ["cancel", "cancelled", "cancellation", "missed trip"],
        "evidence_focus": ["booking confirmation", "cancellation evidence", "covered reason"],
        "fallback_rationale": "The claim text suggests trip cancellation, so planning emphasizes booking and cancellation evidence.",
        "theme_rationale": "The claim appears trip-cancellation related, so planning emphasizes booking and cancellation evidence.",
    },
}

HOME_RULES_BY_CLAIM_TYPE: dict[str, list[str]] = {
    "water_damage": [
        "water_damage_may_be_covered_when_caused_by_sudden_escape_of_water",
        "gradual_leakage_rot_or_poor_maintenance_may_be_excluded",
        "damage_to_the_pipe_or_apparatus_itself_may_be_excluded",
        "plumber_report_or_cause_confirmation_is_often_required",
    ],
    "storm_damage": [
        "storm_or_flood_coverage_must_be_separated_from_wear_and_tear",
        "weather_evidence_may_be_required",
        "pre_existing_roof_damage_or_poor_maintenance_may_be_excluded",
    ],
    "theft": [
        "theft_usually_requires_police_report",
        "forcible_or_violent_entry_may_be_required",
        "proof_of_ownership_may_be_required_for_stolen_items",
    ],
    "fire_damage": [
        "fire_damage_requires_incident_evidence",
        "smoke_damage_arising_gradually_may_be_excluded",
    ],
    "broken_glass": [
        "broken_glass_may_be_separately_covered",
        "damage_photos_and_repair_estimate_are_expected",
    ],
}

HOME_CHECKLIST_BY_CLAIM_TYPE: dict[str, list[FunctionalChecklistItem]] = {
    "water_damage": [
        {"check": "sudden_escape_of_water", "target_agent": "CoverageMatchingAgent"},
        {"check": "gradual_leakage_or_rot", "target_agent": "ExclusionCheckingAgent"},
        {"check": "pipe_or_apparatus_itself", "target_agent": "ExclusionCheckingAgent"},
        {"check": "plumber_report", "target_agent": "MissingDocumentsAgent"},
        {"check": "repair_estimate", "target_agent": "MissingDocumentsAgent"},
    ],
    "storm_damage": [
        {"check": "weather_event", "target_agent": "CoverageMatchingAgent"},
        {"check": "wear_and_tear", "target_agent": "ExclusionCheckingAgent"},
        {"check": "weather_report", "target_agent": "MissingDocumentsAgent"},
    ],
    "theft": [
        {"check": "forcible_entry", "target_agent": "CoverageMatchingAgent"},
        {"check": "police_report", "target_agent": "MissingDocumentsAgent"},
        {"check": "proof_of_ownership", "target_agent": "MissingDocumentsAgent"},
    ],
}

PLANNING_SIGNALS_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "claim_theme": {
            "type": "string",
            "enum": [
                "theft",
                "storm_damage",
                "water_damage",
                "fire_damage",
                "vehicle_damage",
                "medical",
                "baggage_loss",
                "trip_cancellation",
                "unknown",
            ],
        },
        "evidence_focus": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 5,
        },
        "rationale": {"type": "string"},
    },
    "required": ["claim_theme", "evidence_focus", "rationale"],
}

UNKNOWN_THEME = "unknown"
UNKNOWN_THEME_RATIONALE = "The claim type is not obvious from text, so the complete validation path is kept."

__all__ = [
    "CLAIM_THEME_CONFIG",
    "HOME_CHECKLIST_BY_CLAIM_TYPE",
    "HOME_RULES_BY_CLAIM_TYPE",
    "PLANNING_SIGNALS_JSON_SCHEMA",
    "UNKNOWN_THEME",
    "UNKNOWN_THEME_RATIONALE",
]

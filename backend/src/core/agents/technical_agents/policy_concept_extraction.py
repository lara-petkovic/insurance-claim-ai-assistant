from typing import Any

from core.agents.technical_agents.shared import *


class PolicyConceptExtractionAgent(BaseAgent):
    """Extracts normalized coverage, exclusion, and policy-condition concepts."""

    name = "PolicyConceptExtractionAgent"

    COVERAGE_PATTERNS = {
        "fire_damage": ["fire", "smoke", "explosion", "lightning"],
        "storm_damage": ["storm", "flood", "weather"],
        "theft": ["theft", "attempted theft", "stolen", "forcible"],
        "water_damage": ["escape of water", "water installation", "pipe", "leak", "washing machine"],
        "broken_glass": ["breakage", "fixed glass", "sanitary ware", "glass"],
        "vehicle_damage": ["vehicle", "car", "collision", "accidental damage", "comprehensive"],
        "medical": ["medical", "hospital", "emergency treatment", "doctor", "illness"],
        "baggage_loss": ["baggage", "luggage", "personal belongings", "lost luggage"],
        "trip_cancellation": ["trip cancellation", "cancellation", "curtailment", "covered reason"],
    }

    EXCLUSION_PATTERNS = {
        "unoccupied_home": ["unoccupied", "unfurnished"],
        "gradual_damage": ["gradual", "repeated exposure", "long-term", "wear and tear"],
        "rot": ["rot"],
        "poor_maintenance": ["poor maintenance", "lack of maintenance"],
        "pipe_or_apparatus_itself": ["apparatus", "pipes from which the water escaped"],
        "subsidence_landslip": ["subsidence", "landslip", "ground heave"],
        "mechanical_breakdown": ["mechanical breakdown", "wear and tear"],
        "unattended_baggage": ["unattended baggage", "left unattended"],
        "pre_existing_medical": ["pre-existing", "pre existing", "known medical condition"],
    }

    def run(self, context: AgentContext) -> AgentResponse:
        policy_text = context.memory.get("DocumentIngestionAgent", {}).get("policy_text", "")
        lower = policy_text.lower()

        covered_events = [
            {"concept": concept, "matched_terms": [term for term in terms if term in lower]}
            for concept, terms in self.COVERAGE_PATTERNS.items()
            if any(term in lower for term in terms)
        ]
        exclusions = [
            {"concept": concept, "matched_terms": [term for term in terms if term in lower]}
            for concept, terms in self.EXCLUSION_PATTERNS.items()
            if any(term in lower for term in terms)
        ]

        required_documents = ["claim description", "damage photos"]
        if "repair estimate" in lower or "invoice" in lower:
            required_documents.append("repair estimate or invoice")
        if "police report" in lower:
            required_documents.append("police report for theft")
        if "weather" in lower:
            required_documents.append("weather evidence for storm claims")

        policy_period = None
        date_match = re.search(r"(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2}).{0,80}(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})", policy_text)
        if date_match:
            policy_period = {"start": date_match.group(1), "end": date_match.group(2)}

        findings = {
            "policy_type": "home_insurance",
            "policy_period": policy_period,
            "insured_subject": {"type": "home_or_personal_property", "source": "policy"},
            "covered_events": covered_events,
            "exclusions": exclusions,
            "limits": [],
            "deductible_or_excess": "excess mentioned in policy wording" if "excess" in lower else None,
            "required_claim_documents": required_documents,
            "special_conditions": ["policy wording structure normalized into shared concept schema"],
        }
        fallback = findings
        model_client = get_model_client()
        model_result = model_client.json_response(
            system=(
                "You are an insurance policy concept extraction agent. "
                "Return only valid JSON. Normalize heterogeneous policy wording into a shared insurance schema."
            ),
            prompt=(
                "Extract normalized insurance policy concepts from this policy text. "
                "Use this exact top-level JSON shape: "
                "{policy_type, policy_period, insured_subject, covered_events, exclusions, limits, "
                "deductible_or_excess, required_claim_documents, special_conditions}. "
                "covered_events and exclusions must be arrays of objects with at least concept and evidence_text.\n\n"
                f"POLICY TEXT:\n{policy_text[:12000]}"
            ),
            fallback=fallback,
        )
        findings: dict[str, Any] = {**fallback, **model_result.data, "model_used": model_result.used_model}
        findings["covered_events"] = _merge_dict_lists_by_key(
            covered_events,
            model_result.data.get("covered_events"),
        )
        findings["exclusions"] = _merge_dict_lists_by_key(
            exclusions,
            model_result.data.get("exclusions"),
        )
        return self.respond(
            findings=findings,
            confidence=0.78 if covered_events else 0.45,
            warnings=(
                ["Used configured model for policy concept extraction."]
                if model_result.used_model
                else ([] if covered_events else ["No covered events were confidently extracted."])
            ),
            requires_human_review=not bool(covered_events),
            messages=[
                self.message(
                    f"Normalized {len(findings.get('covered_events', []))} covered event(s) and {len(findings.get('exclusions', []))} exclusion concept(s).",
                    to_agent="CoverageMatchingAgent",
                    message_type="handoff",
                    metadata={
                        "covered_events": findings.get("covered_events", []),
                        "exclusions": findings.get("exclusions", []),
                    },
                ),
                self.message(
                    "Policy exclusions are ready for targeted exclusion review.",
                    to_agent="ExclusionCheckingAgent",
                    message_type="request",
                    metadata={"exclusions": findings.get("exclusions", [])},
                ),
            ],
        )

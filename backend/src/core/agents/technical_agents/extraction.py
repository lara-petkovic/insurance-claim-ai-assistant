from core.agents.technical_agents.shared import *

class PolicyConceptExtractionAgent(BaseAgent):
    name = "PolicyConceptExtractionAgent"

    COVERAGE_PATTERNS = {
        "fire_damage": ["fire", "smoke", "explosion", "lightning"],
        "storm_damage": ["storm", "flood", "weather"],
        "theft": ["theft", "attempted theft", "stolen", "forcible"],
        "water_damage": ["escape of water", "water installation", "pipe", "leak", "washing machine"],
        "broken_glass": ["breakage", "fixed glass", "sanitary ware", "glass"],
    }

    EXCLUSION_PATTERNS = {
        "unoccupied_home": ["unoccupied", "unfurnished"],
        "gradual_damage": ["gradual", "repeated exposure", "long-term", "wear and tear"],
        "rot": ["rot"],
        "poor_maintenance": ["poor maintenance", "lack of maintenance"],
        "pipe_or_apparatus_itself": ["apparatus", "pipes from which the water escaped"],
        "subsidence_landslip": ["subsidence", "landslip", "ground heave"],
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
        findings = {**fallback, **model_result.data, "model_used": model_result.used_model}
        findings["covered_events"] = _merge_dict_lists_by_key(
            covered_events,
            model_result.data.get("covered_events"),
        )
        findings["exclusions"] = _merge_dict_lists_by_key(
            exclusions,
            model_result.data.get("exclusions"),
        )
        return AgentResponse(
            agent_name=self.name,
            findings=findings,
            confidence=0.78 if covered_events else 0.45,
            warnings=(
                ["Used configured model provider for policy concept extraction."]
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

class ClaimExtractionAgent(BaseAgent):
    name = "ClaimExtractionAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        description = context.request.claim_description
        text = description.lower()
        claim_type = "unknown"
        if _contains(text, "pipe", "leak", "water", "ceiling", "bathroom", "flooded"):
            claim_type = "water_damage"
        elif _contains(text, "storm", "wind", "roof", "hail", "attic"):
            claim_type = "storm_damage"
        elif _contains(text, "stole", "stolen", "theft", "break", "broke into", "burglar"):
            claim_type = "theft"
        elif _contains(text, "fire", "smoke", "burn"):
            claim_type = "fire_damage"
        elif _contains(text, "glass", "window", "sanitary"):
            claim_type = "broken_glass"

        amount_match = re.search(r"([$EUReurRSD\s]*\d[\d,.]*)", description)
        findings = {
            "claim_type": claim_type,
            "incident_date": context.request.incident_date,
            "incident_location": "insured_property" if _contains(text, "home", "house", "bathroom", "kitchen", "roof") else "unknown",
            "damage_or_loss_type": claim_type,
            "claimed_cause": description,
            "claimed_amount": amount_match.group(1).strip() if amount_match else None,
            "user_provided_evidence": {
                "has_image": bool(context.request.damage_image_filename),
                "supporting_documents": context.request.supporting_document_names,
            },
        }
        fallback = findings
        model_client = get_model_client()
        model_result = model_client.json_response(
            system=(
                "You are an insurance claim extraction agent. "
                "Return only valid JSON using the requested schema."
            ),
            prompt=(
                "Extract structured claim facts from this description. "
                "Use this exact top-level JSON shape: "
                "{claim_type, incident_date, incident_location, damage_or_loss_type, "
                "claimed_cause, claimed_amount, user_provided_evidence}. "
                "claim_type should be one of water_damage, storm_damage, theft, fire_damage, "
                "broken_glass, vehicle_damage, medical, baggage_loss, unknown.\n\n"
                f"INCIDENT DATE FIELD: {context.request.incident_date}\n"
                f"SUPPORTING DOCUMENT NAMES: {context.request.supporting_document_names}\n"
                f"DAMAGE IMAGE FILENAME: {context.request.damage_image_filename}\n"
                f"CLAIM DESCRIPTION:\n{description}"
            ),
            fallback=fallback,
        )
        findings = {**fallback, **model_result.data, "model_used": model_result.used_model}
        claim_type = str(findings.get("claim_type", claim_type))
        return AgentResponse(
            agent_name=self.name,
            findings=findings,
            confidence=0.82 if claim_type != "unknown" else 0.35,
            warnings=(
                ["Used configured model provider for claim extraction."]
                if model_result.used_model
                else ([] if claim_type != "unknown" else ["Could not classify claim type from description."])
            ),
            requires_human_review=claim_type == "unknown",
            messages=[
                self.message(
                    f"Claim facts extracted and classified as {claim_type}.",
                    to_agent="HomeInsuranceFunctionalAgent",
                    message_type="handoff",
                    metadata={"claim_type": claim_type, "incident_date": findings.get("incident_date")},
                ),
                self.message(
                    "Claim facts are ready for retrieval and coverage matching.",
                    to_agent="RetrievalAgent",
                    message_type="handoff",
                    metadata={"claim_type": claim_type, "description": description},
                ),
            ],
        )


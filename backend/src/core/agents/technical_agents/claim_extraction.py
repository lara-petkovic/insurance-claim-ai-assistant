import re
from typing import Any

from core.agents.base import AgentContext, BaseAgent
from core.agents.technical_agents.shared import _contains, specialized_functional_agent_name
from core.models.agent import AgentResponse
from models.model_client import get_model_client


class ClaimExtractionAgent(BaseAgent):
    """Extracts structured claim facts and classifies the claim type."""

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
        elif _contains(text, "car", "vehicle", "collision", "crash", "accident", "bumper"):
            claim_type = "vehicle_damage"
        elif _contains(text, "fire", "smoke", "burn"):
            claim_type = "fire_damage"
        elif _contains(text, "doctor", "hospital", "medical", "illness", "injury", "ambulance"):
            claim_type = "medical"
        elif _contains(text, "baggage", "luggage", "suitcase", "lost bag"):
            claim_type = "baggage_loss"
        elif _contains(text, "cancel", "cancelled", "cancellation", "missed trip"):
            claim_type = "trip_cancellation"
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
        findings: dict[str, Any] = {**fallback, **model_result.data, "model_used": model_result.used_model}
        claim_type = str(findings.get("claim_type", claim_type))
        return self.respond(
            findings=findings,
            confidence=0.82 if claim_type != "unknown" else 0.35,
            warnings=(
                ["Used configured model for claim extraction."]
                if model_result.used_model
                else ([] if claim_type != "unknown" else ["Could not classify claim type from description."])
            ),
            requires_human_review=claim_type == "unknown",
            messages=[
                self.message(
                    f"Claim facts extracted and classified as {claim_type}.",
                    to_agent=specialized_functional_agent_name(context.request.insurance_type),
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

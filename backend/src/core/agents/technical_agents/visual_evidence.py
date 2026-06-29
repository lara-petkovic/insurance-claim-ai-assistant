from core.agents.technical_agents.shared import *


class VisualEvidenceAgent(BaseAgent):
    """Assesses uploaded damage images and classifies visible insurance damage."""

    name = "VisualEvidenceAgent"

    LABEL_KEYWORDS = {
        "water_damage": ["water", "leak", "ceiling", "mold", "wet", "pipe"],
        "fire_damage": ["fire", "smoke", "burn"],
        "storm_damage": ["storm", "roof", "hail", "wind"],
        "broken_glass": ["glass", "window", "broken"],
        "theft_damage": ["theft", "stolen", "breakin", "burglary"],
        "vehicle_damage": ["car", "vehicle", "auto"],
    }

    def run(self, context: AgentContext) -> AgentResponse:
        filename = (context.request.damage_image_filename or "").lower()
        detected = "unknown"
        for label, keywords in self.LABEL_KEYWORDS.items():
            if any(keyword in filename for keyword in keywords):
                detected = label
                break

        if not filename:
            warning = "No damage image was uploaded."
            confidence = 0.0
        elif detected == "unknown":
            warning = "Image classification is inconclusive without a successful vision model response."
            confidence = 0.3
        else:
            warning = ""
            confidence = 0.72

        findings = ImageAssessment(
            detected_damage=detected,
            confidence=confidence,
            notes=["Fallback classification is used only when model fallback mode is explicitly enabled."],
        ).model_dump()
        model_client = get_model_client()
        model_result = model_client.image_json_response(
            system=(
                "You are a visual insurance evidence agent. "
                "Inspect the image and return only valid JSON."
            ),
            prompt=(
                "Classify visible insurance damage. Use this exact JSON shape: "
                "{detected_damage, confidence, notes}. detected_damage should be one of "
                "water_damage, fire_damage, storm_damage, broken_glass, theft_damage, "
                "vehicle_damage, unknown. confidence must be a number between 0 and 1."
            ),
            image_bytes=context.request.damage_image_bytes,
            image_mime_type=context.request.damage_image_mime_type,
            fallback=findings,
        )
        findings = {**findings, **model_result.data, "model_used": model_result.used_model}
        findings["notes"] = [str(note) for note in _as_list(findings.get("notes"))]
        detected = str(findings.get("detected_damage", detected))
        confidence = float(findings.get("confidence", confidence) or 0)
        return self.respond(
            findings=findings,
            confidence=confidence,
            warnings=(
                ["Used configured vision-capable model for visual evidence assessment."]
                if model_result.used_model
                else ([warning] if warning else [])
            ),
            requires_human_review=detected == "unknown",
            messages=[
                self.message(
                    f"Visual evidence assessed as {detected}.",
                    to_agent="ConsistencyVerificationAgent",
                    message_type="handoff",
                    metadata={"detected_damage": detected, "confidence": confidence},
                )
            ],
        )

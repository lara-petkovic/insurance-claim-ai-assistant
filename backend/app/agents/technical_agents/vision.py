from app.agents.technical_agents.shared import *

class VisualEvidenceAgent(BaseAgent):
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
        return AgentResponse(
            agent_name=self.name,
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

class ImageAuthenticityAgent(BaseAgent):
    name = "ImageAuthenticityAgent"

    def run(self, context: AgentContext) -> AgentResponse:
        filename = context.request.damage_image_filename or ""
        suffix = Path(filename).suffix.lower()
        signals: list[str] = []
        score = 0.1
        if not filename:
            signals.append("no_image_uploaded")
            score = 0.6
        if suffix and suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            signals.append("unusual_file_extension")
            score += 0.25
        if context.request.damage_image_size is not None and context.request.damage_image_size < 8_000:
            signals.append("very_small_image_file")
            score += 0.2
        if _contains(filename, "ai", "generated", "edited", "fake", "photoshop"):
            signals.append("suspicious_filename")
            score += 0.35
        if filename and "metadata" not in filename.lower():
            signals.append("metadata_not_available_in_mvp_upload")
            score += 0.05

        score = min(round(score, 2), 1.0)
        if score >= 0.75:
            risk = "requires_human_review"
        elif score >= 0.5:
            risk = "high"
        elif score >= 0.25:
            risk = "medium"
        else:
            risk = "low"

        findings = ImageAuthenticity(risk_level=risk, risk_score=score, signals=signals).model_dump()
        model_client = get_model_client()
        model_result = model_client.image_json_response(
            system=(
                "You are an insurance image authenticity risk agent. "
                "Return only valid JSON. Do not claim certainty; estimate risk signals."
            ),
            prompt=(
                "Assess whether this insurance claim image has authenticity risks. "
                "Use this exact JSON shape: {risk_level, risk_score, signals}. "
                "risk_level must be low, medium, high, or requires_human_review. "
                "risk_score must be a number between 0 and 1. signals must be short textual observations."
            ),
            image_bytes=context.request.damage_image_bytes,
            image_mime_type=context.request.damage_image_mime_type,
            fallback=findings,
        )
        findings = {**findings, **model_result.data, "model_used": model_result.used_model}
        findings["signals"] = [str(signal) for signal in _as_list(findings.get("signals"))]
        risk = str(findings.get("risk_level", risk))
        return AgentResponse(
            agent_name=self.name,
            findings=findings,
            confidence=0.6,
            warnings=(
                ["Used configured vision-capable model for image authenticity assessment."]
                if model_result.used_model
                else ["Authenticity assessment did not use a model because no image was uploaded or fallback mode is enabled."]
            ),
            requires_human_review=risk in {"high", "requires_human_review"},
            messages=[
                self.message(
                    f"Image authenticity risk estimated as {risk}.",
                    to_agent="OrchestratorAgent",
                    message_type="validation",
                    metadata={"risk_level": risk, "risk_score": findings.get("risk_score"), "signals": findings.get("signals", [])},
                )
            ],
        )


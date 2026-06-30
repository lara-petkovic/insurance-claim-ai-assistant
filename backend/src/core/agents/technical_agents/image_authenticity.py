from pathlib import Path

from core.agents.base import AgentContext, BaseAgent
from core.agents.technical_agents.shared import _as_list, _contains
from core.models.agent import AgentResponse
from core.models.claim import ImageAuthenticity
from models.model_client import get_model_client


class ImageAuthenticityAgent(BaseAgent):
    """Estimates authenticity risk signals for uploaded claim images."""

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
        return self.respond(
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

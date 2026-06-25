from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from config.settings import get_settings
from utils.agent_logger import log_agent_event


class ModelCallError(RuntimeError):
    pass


@dataclass
class ModelResult:
    data: dict[str, Any]
    used_model: bool
    error: str | None = None


class ModelClient:
    """OpenAI-backed adapter used by all semantic agents."""

    def __init__(self) -> None:
        settings = get_settings()
        self.provider = settings.model_provider
        self.require_models = settings.openai_require_models
        self.api_key = settings.openai_api_key
        self.text_model = settings.openai_text_model
        self.vision_model = settings.openai_vision_model

        self._client: Any = None
        self.init_error: str | None = None

        if self.api_key and self.api_key != "your_api_key_here":
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key)
                log_agent_event(
                    "ModelClient",
                    "OpenAI client initialized.",
                    text_model=self.text_model,
                    vision_model=self.vision_model,
                    require_models=self.require_models,
                )
            except Exception as exc:
                self.init_error = str(exc)
                log_agent_event("ModelClient", "OpenAI client initialization failed.", error=self.init_error)
        else:
            self.init_error = "OPENAI_API_KEY is not configured. Replace 'your_api_key_here' in backend/.env."
            log_agent_event("ModelClient", "OpenAI API key is not configured.")

    @property
    def available(self) -> bool:
        return self._client is not None

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "client_available": self.available,
            "require_models": self.require_models,
            "openai_configured": bool(self.api_key and self.api_key != "your_api_key_here"),
            "text_model": self.text_model,
            "vision_model": self.vision_model,
            "init_error": self.init_error,
        }

    def json_response(
        self,
        *,
        system: str,
        prompt: str,
        fallback: dict[str, Any],
        model: str | None = None,
    ) -> ModelResult:
        if not self._client:
            return self._fallback_or_raise(fallback, self.init_error or "Model client is unavailable.")
        return self._openai_json_response(system=system, prompt=prompt, fallback=fallback, model=model)

    def image_json_response(
        self,
        *,
        system: str,
        prompt: str,
        image_bytes: bytes | None,
        image_mime_type: str | None,
        fallback: dict[str, Any],
    ) -> ModelResult:
        if not image_bytes or not image_mime_type:
            return ModelResult(data=fallback, used_model=False, error="No image bytes were provided.")
        if not self._client:
            return self._fallback_or_raise(fallback, self.init_error or "Model client is unavailable.")
        return self._openai_image_json_response(
            system=system,
            prompt=prompt,
            image_bytes=image_bytes,
            image_mime_type=image_mime_type,
            fallback=fallback,
        )

    def text_response(self, *, prompt: str, system: str | None = None, model: str | None = None) -> ModelResult:
        fallback = {"answer": ""}
        system_prompt = system or "You are a concise assistant."
        if not self._client:
            return self._fallback_or_raise(fallback, self.init_error or "Model client is unavailable.")

        try:
            selected_model = model or self.text_model
            log_agent_event("ModelClient", "Calling OpenAI text model.", model=selected_model, prompt_chars=len(prompt))
            response = self._client.responses.create(
                model=selected_model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            log_agent_event("ModelClient", "OpenAI text model completed.", model=selected_model)
            return ModelResult(data={"answer": getattr(response, "output_text", "") or ""}, used_model=True)
        except Exception as exc:
            log_agent_event("ModelClient", "OpenAI text model failed.", error=str(exc))
            return self._fallback_or_raise(fallback, f"OpenAI model call failed: {exc}")

    def _openai_json_response(
        self,
        *,
        system: str,
        prompt: str,
        fallback: dict[str, Any],
        model: str | None = None,
    ) -> ModelResult:
        try:
            selected_model = model or self.text_model
            log_agent_event("ModelClient", "Calling OpenAI JSON model.", model=selected_model, prompt_chars=len(prompt))
            response = self._client.responses.create(
                model=selected_model,
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            )
            parsed = self._extract_json(getattr(response, "output_text", "") or "")
            if parsed is None:
                log_agent_event("ModelClient", "OpenAI JSON model returned invalid JSON.", model=selected_model)
                return self._fallback_or_raise(fallback, "OpenAI model returned invalid JSON.")
            log_agent_event("ModelClient", "OpenAI JSON model completed.", model=selected_model, keys=len(parsed))
            return ModelResult(data=parsed, used_model=True)
        except Exception as exc:
            log_agent_event("ModelClient", "OpenAI JSON model failed.", error=str(exc))
            return self._fallback_or_raise(fallback, f"OpenAI model call failed: {exc}")

    def _openai_image_json_response(
        self,
        *,
        system: str,
        prompt: str,
        image_bytes: bytes,
        image_mime_type: str,
        fallback: dict[str, Any],
    ) -> ModelResult:
        data_url = f"data:{image_mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        try:
            log_agent_event(
                "ModelClient",
                "Calling OpenAI vision model.",
                model=self.vision_model,
                image_bytes=len(image_bytes),
                image_type=image_mime_type,
            )
            response = self._client.responses.create(
                model=self.vision_model,
                input=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": prompt},
                            {"type": "input_image", "image_url": data_url},
                        ],
                    },
                ],
            )
            parsed = self._extract_json(getattr(response, "output_text", "") or "")
            if parsed is None:
                log_agent_event("ModelClient", "OpenAI vision model returned invalid JSON.", model=self.vision_model)
                return self._fallback_or_raise(fallback, "OpenAI vision model returned invalid JSON.")
            log_agent_event("ModelClient", "OpenAI vision model completed.", model=self.vision_model, keys=len(parsed))
            return ModelResult(data=parsed, used_model=True)
        except Exception as exc:
            log_agent_event("ModelClient", "OpenAI vision model failed.", error=str(exc))
            return self._fallback_or_raise(fallback, f"OpenAI vision model call failed: {exc}")

    def _fallback_or_raise(self, fallback: dict[str, Any], error: str) -> ModelResult:
        if self.require_models:
            raise ModelCallError(error)
        return ModelResult(data=fallback, used_model=False, error=error)

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any] | None:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.removeprefix("json").strip()

        try:
            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(cleaned[start : end + 1])
                    return parsed if isinstance(parsed, dict) else None
                except json.JSONDecodeError:
                    return None
        return None


@lru_cache
def get_model_client() -> ModelClient:
    return ModelClient()

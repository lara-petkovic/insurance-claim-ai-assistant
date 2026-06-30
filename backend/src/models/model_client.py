from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from config import get_settings
from utils.app_logger import get_logger, log_event

logger = get_logger("model_client")


class ModelCallError(RuntimeError):
    pass


@dataclass
class ModelResult:
    data: dict[str, Any]
    used_model: bool
    error: str | None = None


ResponseModel = type[Any]


class ModelClient:
    """OpenAI-backed adapter used by all semantic agents."""

    def __init__(self) -> None:
        settings = get_settings()
        self.require_models = settings.openai_require_models
        self.api_key = settings.openai_api_key
        self.text_model = settings.openai_text_model
        self.planning_model = settings.openai_planning_model
        self.vision_model = settings.openai_vision_model

        self._client: Any = None
        self.init_error: str | None = None

        if self.api_key and self.api_key != "your_api_key_here":
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key)
                log_event(
                    logger,
                    "OpenAI client initialized.",
                    text_model=self.text_model,
                    planning_model=self.planning_model,
                    vision_model=self.vision_model,
                    require_models=self.require_models,
                )
            except Exception as exc:
                self.init_error = str(exc)
                log_event(logger, "OpenAI client initialization failed.", error=self.init_error)
        else:
            self.init_error = "OPENAI_API_KEY is not configured in the process environment."
            log_event(logger, "OpenAI API key is not configured.")

    def json_response(
        self,
        *,
        system: str,
        prompt: str,
        fallback: dict[str, Any],
        model: str | None = None,
        schema_name: str | None = None,
        json_schema: dict[str, Any] | None = None,
        response_model: ResponseModel | None = None,
        schema_description: str | None = None,
        strict_schema: bool = True,
    ) -> ModelResult:
        if not self._client:
            return self._fallback_or_raise(fallback, self.init_error or "Model client is unavailable.")
        return self._create_json_response(
            call_label="OpenAI JSON model",
            invalid_json_error="OpenAI model returned invalid JSON.",
            model=model or self.text_model,
            input_payload=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            fallback=fallback,
            prompt_chars=len(prompt),
            schema_name=schema_name,
            json_schema=json_schema,
            response_model=response_model,
            schema_description=schema_description,
            strict_schema=strict_schema,
        )

    def image_json_response(
        self,
        *,
        system: str,
        prompt: str,
        image_bytes: bytes | None,
        image_mime_type: str | None,
        fallback: dict[str, Any],
        schema_name: str | None = None,
        json_schema: dict[str, Any] | None = None,
        response_model: ResponseModel | None = None,
        schema_description: str | None = None,
        strict_schema: bool = True,
    ) -> ModelResult:
        if not image_bytes or not image_mime_type:
            return ModelResult(data=fallback, used_model=False, error="No image bytes were provided.")
        if not self._client:
            return self._fallback_or_raise(fallback, self.init_error or "Model client is unavailable.")
        image_url = f"data:{image_mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        return self._create_json_response(
            call_label="OpenAI vision model",
            invalid_json_error="OpenAI vision model returned invalid JSON.",
            model=self.vision_model,
            input_payload=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": image_url},
                    ],
                },
            ],
            fallback=fallback,
            prompt_chars=len(prompt),
            input_details={"image_bytes": len(image_bytes), "image_type": image_mime_type},
            schema_name=schema_name,
            json_schema=json_schema,
            response_model=response_model,
            schema_description=schema_description,
            strict_schema=strict_schema,
        )

    def file_json_response(
        self,
        *,
        system: str,
        prompt: str,
        file_bytes: bytes | None,
        file_mime_type: str,
        filename: str,
        fallback: dict[str, Any],
        schema_name: str | None = None,
        json_schema: dict[str, Any] | None = None,
        response_model: ResponseModel | None = None,
        schema_description: str | None = None,
        strict_schema: bool = True,
        detail: str = "high",
    ) -> ModelResult:
        if not file_bytes:
            return ModelResult(data=fallback, used_model=False, error="No file bytes were provided.")
        if not self._client:
            return self._fallback_or_raise(fallback, self.init_error or "Model client is unavailable.")
        file_data = f"data:{file_mime_type};base64,{base64.b64encode(file_bytes).decode('ascii')}"
        return self._create_json_response(
            call_label="OpenAI file extraction model",
            invalid_json_error="OpenAI file extraction model returned invalid JSON.",
            model=self.vision_model,
            input_payload=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_file",
                            "filename": filename,
                            "file_data": file_data,
                            "detail": detail,
                        },
                    ],
                },
            ],
            fallback=fallback,
            prompt_chars=len(prompt),
            input_details={"file_bytes": len(file_bytes), "file_type": file_mime_type},
            schema_name=schema_name,
            json_schema=json_schema,
            response_model=response_model,
            schema_description=schema_description,
            strict_schema=strict_schema,
        )

    def _create_json_response(
        self,
        *,
        call_label: str,
        invalid_json_error: str,
        model: str,
        input_payload: list[dict[str, Any]],
        fallback: dict[str, Any],
        prompt_chars: int,
        input_details: dict[str, Any] | None = None,
        schema_name: str | None = None,
        json_schema: dict[str, Any] | None = None,
        response_model: ResponseModel | None = None,
        schema_description: str | None = None,
        strict_schema: bool = True,
    ) -> ModelResult:
        try:
            text_config = self._structured_text_config(
                schema_name=schema_name,
                json_schema=json_schema,
                response_model=response_model,
                schema_description=schema_description,
                strict_schema=strict_schema,
            )
            log_event(
                logger,
                f"Calling {call_label}.",
                model=model,
                prompt_chars=prompt_chars,
                **(input_details or {}),
                structured_output=bool(text_config),
                schema_name=self._schema_name(schema_name=schema_name, response_model=response_model) if text_config else None,
            )
            create_kwargs: dict[str, Any] = {
                "model": model,
                "input": input_payload,
            }
            if text_config:
                create_kwargs["text"] = text_config
            response = self._client.responses.create(**create_kwargs)
            parsed = self._parse_model_json(
                getattr(response, "output_text", "") or "",
                structured_output=bool(text_config),
                response_model=response_model,
            )
            if parsed is None:
                log_event(logger, invalid_json_error, model=model)
                return self._fallback_or_raise(fallback, invalid_json_error)
            log_event(
                logger,
                f"{call_label} completed.",
                model=model,
                keys=len(parsed),
                structured_output=bool(text_config),
            )
            return ModelResult(data=parsed, used_model=True)
        except ModelCallError:
            raise
        except Exception as exc:
            log_event(logger, f"{call_label} failed.", error=str(exc))
            return self._fallback_or_raise(fallback, f"{call_label} call failed: {exc}")

    def _fallback_or_raise(self, fallback: dict[str, Any], error: str) -> ModelResult:
        if self.require_models:
            raise ModelCallError(error)
        return ModelResult(data=fallback, used_model=False, error=error)

    def _structured_text_config(
        self,
        *,
        schema_name: str | None,
        json_schema: dict[str, Any] | None,
        response_model: ResponseModel | None,
        schema_description: str | None,
        strict_schema: bool,
    ) -> dict[str, Any] | None:
        schema = json_schema or self._schema_from_response_model(response_model)
        if not schema:
            return None
        name = self._schema_name(schema_name=schema_name, response_model=response_model)
        return {
            "format": {
                "type": "json_schema",
                "name": name,
                "schema": schema,
                "strict": strict_schema,
                **({"description": schema_description} if schema_description else {}),
            }
        }

    @staticmethod
    def _schema_name(*, schema_name: str | None, response_model: ResponseModel | None) -> str:
        if schema_name:
            return schema_name
        if response_model:
            return getattr(response_model, "__name__", "structured_response")
        return "structured_response"

    @staticmethod
    def _schema_from_response_model(response_model: ResponseModel | None) -> dict[str, Any] | None:
        if response_model is None:
            return None
        if hasattr(response_model, "model_json_schema"):
            return response_model.model_json_schema()
        if hasattr(response_model, "schema"):
            return response_model.schema()
        raise TypeError("response_model must be a Pydantic model class with a JSON schema method.")

    def _parse_model_json(
        self,
        text: str,
        *,
        structured_output: bool,
        response_model: ResponseModel | None,
    ) -> dict[str, Any] | None:
        parsed = self._parse_strict_json(text) if structured_output else self._extract_json(text)
        if parsed is None:
            return None
        if response_model is None:
            return parsed
        if hasattr(response_model, "model_validate"):
            return response_model.model_validate(parsed).model_dump()
        if hasattr(response_model, "parse_obj"):
            return response_model.parse_obj(parsed).dict()
        raise TypeError("response_model must be a Pydantic model class with a validation method.")

    @staticmethod
    def _parse_strict_json(text: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

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
            if 0 <= start < end:
                try:
                    parsed = json.loads(cleaned[start : end + 1])
                    return parsed if isinstance(parsed, dict) else None
                except json.JSONDecodeError:
                    return None
        return None


@lru_cache
def get_model_client() -> ModelClient:
    return ModelClient()

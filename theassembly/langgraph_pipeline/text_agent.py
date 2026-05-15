from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError


class TextAgentError(RuntimeError):
    pass


T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class TextAgentResult:
    payload: dict[str, Any]
    model: str
    usage: dict[str, Any]


def _extract_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text.strip():
                return part_text.strip()

    raise TextAgentError("Text agent did not return text content")


def _extract_usage(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return {}
    data: dict[str, Any] = {}
    for key in (
        "prompt_token_count",
        "candidates_token_count",
        "total_token_count",
        "cached_content_token_count",
    ):
        value = getattr(usage, key, None)
        if value is not None:
            data[key] = value
    return data


def _parse_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def call_text_agent(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    response_model: type[T],
    temperature: float,
    max_output_tokens: int,
) -> TextAgentResult:
    try:
        from google import genai
        from google.genai import types
    except Exception as exc:  # pragma: no cover
        raise TextAgentError("google-genai is not installed") from exc

    schema = response_model.model_json_schema()
    full_prompt = (
        f"{system_prompt}\n\n"
        "Return valid JSON only, no markdown, no prose.\n"
        f"JSON_SCHEMA:\n{json.dumps(schema, separators=(',', ':'))}\n\n"
        f"{user_prompt}"
    )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=full_prompt,
        config=types.GenerateContentConfig(
            temperature=max(0.0, min(temperature, 1.0)),
            response_mime_type="application/json",
            max_output_tokens=max(128, max_output_tokens),
        ),
    )

    text = _extract_text(response)
    try:
        data = _parse_json(text)
    except Exception as exc:
        raise TextAgentError(f"text agent returned non-JSON output: {exc}") from exc

    try:
        validated = response_model.model_validate(data)
    except ValidationError as exc:
        raise TextAgentError(f"text agent schema validation failed: {exc}") from exc

    return TextAgentResult(
        payload=validated.model_dump(by_alias=True),
        model=model,
        usage=_extract_usage(response),
    )

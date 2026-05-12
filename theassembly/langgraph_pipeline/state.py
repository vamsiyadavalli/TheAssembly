from __future__ import annotations

from typing import Any, TypedDict


class PosterState(TypedDict, total=False):
    raw_wod: dict[str, Any]
    validated_wod: dict[str, Any]
    strategic_intent: str
    layout_coordinates: dict[str, Any]
    brand_assets: dict[str, Any]
    final_graphic_prompt: str
    image_path: str
    image_metrics: dict[str, int]
    validation_result: dict[str, Any]
    similarity_score: float
    feedback: str
    retry_count: int
    max_retries: int
    is_valid: bool
    error_log: list[str]

    api_key: str
    model: str
    aspect_ratio: str
    output_path: str
    max_retries_api: int
    max_retry_delay_seconds: float
    retry_jitter_ratio: float

    trace_enabled: bool
    trace_level: str
    save_intermediate_prompts: bool
    redact_secrets: bool
    run_id: str
    run_started_at_utc: str
    run_finished_at_utc: str
    trace_path: str
    node_traces: dict[str, dict[str, Any]]
    retry_history: list[dict[str, Any]]

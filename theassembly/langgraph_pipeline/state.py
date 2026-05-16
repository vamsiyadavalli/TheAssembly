from __future__ import annotations

from typing import Any, TypedDict


class PosterState(TypedDict, total=False):
    raw_wod: dict[str, Any]
    validated_wod: dict[str, Any]
    reasoning_plan: dict[str, Any]
    reasoning_schema_version: str
    reasoning_stage_classification: dict[str, Any]
    reasoning_stage_layout: dict[str, Any]
    reasoning_stage_risks: dict[str, Any]
    canonical_rows: list[dict[str, str]]
    semantic_contract: str
    panel_budgets: dict[str, Any]
    overflow_risks: list[str]
    strategic_intent: str
    layout_coordinates: dict[str, Any]
    brand_assets: dict[str, Any]
    designer_draft: dict[str, Any]
    candidate_graphic_prompt: str
    prompt_rationale: str
    critic_review: dict[str, Any]
    critic_score: int
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
    retry_history: list[dict[str, Any]]
    retry_directives: list[dict[str, Any]]
    last_validation_feedback: dict[str, Any]

    api_key: str
    image_model: str
    reasoning_model: str
    nutrition_model: str
    designer_model: str
    critic_model: str
    critic_enabled: bool
    tier2_starter_enabled: bool
    critic_min_score: int
    reasoning_temperature: float
    designer_temperature: float
    critic_temperature: float
    reasoning_max_output_tokens: int
    designer_max_output_tokens: int
    critic_max_output_tokens: int
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
    llm_models: dict[str, str]
    llm_usage: dict[str, dict[str, Any]]

    # Nutrition baseline (derived artifact, workout-scoped, stateless)
    nutrition_baseline: dict[str, Any]
    nutrition_generation_status: str
    nutrition_feedback: str
    nutrition_artifact_path: str

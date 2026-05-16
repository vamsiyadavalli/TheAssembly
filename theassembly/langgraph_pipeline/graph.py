from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid

from .nodes import (
    architect_node,
    critic_node,
    designer_node,
    editor_node,
    generator_node,
    nutrition_baseline_node,
    reasoning_node,
    should_retry,
    validation_node,
)
from .state import PosterState


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_trace_file(trace: dict[str, Any], output_path: Path) -> Path:
    trace_path = output_path.with_suffix(".trace.json")
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(trace, indent=2, sort_keys=True), encoding="utf-8")
    return trace_path


def _build_trace_document(result: dict[str, Any]) -> dict[str, Any]:
    node_order = ["reasoning", "editor", "architect", "nutrition", "designer", "critic", "generator", "validator"]
    node_traces = result.get("node_traces", {}) if isinstance(result.get("node_traces", {}), dict) else {}
    nodes = {name: node_traces.get(name, {}) for name in node_order if node_traces.get(name)}
    return {
        "schema_version": "1.0.0",
        "run_id": str(result.get("run_id", "")),
        "run_started_at_utc": str(result.get("run_started_at_utc", "")),
        "run_finished_at_utc": _utc_now_iso(),
        "status": "success" if result.get("is_valid") else "failed",
        "retry_count": int(result.get("retry_count", 0)),
        "max_retries": int(result.get("max_retries", 0)),
        "retry_history": list(result.get("retry_history", [])),
        "settings": {
            "trace_level": str(result.get("trace_level", "standard")),
            "save_intermediate_prompts": bool(result.get("save_intermediate_prompts", False)),
            "redact_secrets": bool(result.get("redact_secrets", True)),
            "reasoning_schema_version": str(result.get("reasoning_schema_version", "v1")),
            "tier2_starter_enabled": bool(result.get("tier2_starter_enabled", False)),
            "critic_min_score": int(result.get("critic_min_score", 70)),
            "image_model": str(result.get("image_model", result.get("model", ""))),
            "reasoning_model": str(result.get("reasoning_model", "")),
            "nutrition_model": str(result.get("nutrition_model", "")),
            "designer_model": str(result.get("designer_model", "")),
            "critic_model": str(result.get("critic_model", "")),
            "critic_enabled": bool(result.get("critic_enabled", True)),
            "aspect_ratio": str(result.get("aspect_ratio", "")),
        },
        "nodes": nodes,
        "final": {
            "is_valid": bool(result.get("is_valid", False)),
            "similarity_score": float(result.get("similarity_score", 0.0)),
            "feedback": str(result.get("feedback", "")),
            "image_path": str(result.get("image_path", "")),
            "validation_result": result.get("validation_result", {}),
            "error_log": list(result.get("error_log", [])),
        },
    }


def _compile_graph():
    try:
        from langgraph.graph import END, StateGraph
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("langgraph is not installed. Install it to enable LANGGRAPH_ENABLED mode.") from exc

    workflow = StateGraph(PosterState)
    workflow.add_node("reasoning", reasoning_node)
    workflow.add_node("editor", editor_node)
    workflow.add_node("architect", architect_node)
    workflow.add_node("nutrition", nutrition_baseline_node)
    workflow.add_node("designer", designer_node)
    workflow.add_node("critic", critic_node)
    workflow.add_node("generator", generator_node)
    workflow.add_node("validator", validation_node)

    workflow.set_entry_point("reasoning")
    workflow.add_edge("reasoning", "editor")
    workflow.add_edge("editor", "architect")
    workflow.add_edge("architect", "nutrition")
    workflow.add_edge("nutrition", "designer")
    workflow.add_edge("designer", "critic")
    workflow.add_edge("critic", "generator")
    workflow.add_edge("generator", "validator")

    workflow.add_conditional_edges(
        "validator",
        should_retry,
        {
            "retry": "reasoning",
            "success": END,
            "fail": END,
        },
    )

    return workflow.compile()


def run_poster_pipeline(
    *,
    raw_wod: dict[str, Any],
    output_path: Path,
    api_key: str,
    model: str,
    aspect_ratio: str,
    reasoning_model: str = "models/gemini-2.5-flash",
    nutrition_model: str = "",
    designer_model: str = "models/gemini-2.5-pro",
    critic_model: str = "models/gemini-2.5-pro",
    critic_enabled: bool = True,
    reasoning_temperature: float = 0.1,
    designer_temperature: float = 0.2,
    critic_temperature: float = 0.0,
    reasoning_max_output_tokens: int = 1200,
    designer_max_output_tokens: int = 1800,
    critic_max_output_tokens: int = 1000,
    reasoning_schema_version: str = "v1",
    tier2_starter_enabled: bool = False,
    critic_min_score: int = 70,
    max_retries_api: int,
    max_retry_delay_seconds: float,
    retry_jitter_ratio: float,
    max_validation_retries: int = 3,
    trace_enabled: bool = True,
    trace_level: str = "standard",
    save_intermediate_prompts: bool = False,
    redact_secrets: bool = True,
) -> dict[str, Any]:
    """Run the LangGraph poster pipeline and return final state."""
    graph = _compile_graph()
    run_id = str(uuid.uuid4())
    initial_state: PosterState = {
        "raw_wod": raw_wod,
        "output_path": str(output_path),
        "api_key": api_key,
        "model": model,
        "image_model": model,
        "reasoning_model": reasoning_model,
        "nutrition_model": nutrition_model or reasoning_model,
        "designer_model": designer_model,
        "critic_model": critic_model,
        "critic_enabled": critic_enabled,
        "reasoning_temperature": reasoning_temperature,
        "designer_temperature": designer_temperature,
        "critic_temperature": critic_temperature,
        "reasoning_max_output_tokens": reasoning_max_output_tokens,
        "designer_max_output_tokens": designer_max_output_tokens,
        "critic_max_output_tokens": critic_max_output_tokens,
        "reasoning_schema_version": reasoning_schema_version,
        "tier2_starter_enabled": tier2_starter_enabled,
        "critic_min_score": critic_min_score,
        "aspect_ratio": aspect_ratio,
        "max_retries_api": max_retries_api,
        "max_retry_delay_seconds": max_retry_delay_seconds,
        "retry_jitter_ratio": retry_jitter_ratio,
        "retry_count": 0,
        "max_retries": max_validation_retries,
        "is_valid": False,
        "error_log": [],
        "trace_enabled": trace_enabled,
        "trace_level": trace_level,
        "save_intermediate_prompts": save_intermediate_prompts,
        "redact_secrets": redact_secrets,
        "run_id": run_id,
        "run_started_at_utc": _utc_now_iso(),
        "node_traces": {},
        "llm_models": {},
        "llm_usage": {},
        "retry_history": [],
        "nutrition_baseline": {},
        "nutrition_generation_status": "pending",
        "nutrition_feedback": "",
        "nutrition_artifact_path": "",
    }

    result = graph.invoke(initial_state)
    result_dict = dict(result)
    result_dict["run_finished_at_utc"] = _utc_now_iso()

    if trace_enabled:
        trace = _build_trace_document(result_dict)
        trace_path = _write_trace_file(trace, output_path)
        result_dict["trace_path"] = str(trace_path)

    return result_dict

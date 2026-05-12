from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any

from theassembly.models import WorkoutRecord
from theassembly.workout_image import build_image_prompt, generate_gemini_image

from .state import PosterState
from .tools import (
    ToolExecutionError,
    generate_coordinate_map,
    get_brand_assets,
    validate_workout_schema,
    verify_image_accuracy,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _prompt_trace(system_prompt: str, user_prompt: str, save_text: bool) -> dict[str, Any]:
    combined = f"{system_prompt}\n\n{user_prompt}"
    return {
        "system": system_prompt if save_text else "",
        "user": user_prompt if save_text else "",
        "combined_sha256": _sha256_text(combined),
        "token_estimate": max(1, len(combined) // 4),
    }


def _build_node_trace(
    *,
    node_name: str,
    attempt: int,
    started_at: str,
    started_monotonic: float,
    status: str,
    decision: dict[str, Any],
    prompt: dict[str, Any],
    tools: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    artifacts: list[str] | None = None,
    input_ref: dict[str, Any] | None = None,
    output_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    finished_at = _utc_now_iso()
    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    return {
        "node": node_name,
        "status": status,
        "started_at_utc": started_at,
        "finished_at_utc": finished_at,
        "duration_ms": duration_ms,
        "attempt": attempt,
        "input_ref": input_ref or {},
        "output_ref": output_ref or {},
        "decision": decision,
        "prompt": prompt,
        "tools": tools or [],
        "warnings": warnings or [],
        "errors": errors or [],
        "artifacts": artifacts or [],
    }


def _with_node_trace(state: PosterState, node_name: str, trace: dict[str, Any]) -> dict[str, Any]:
    traces = dict(state.get("node_traces", {}))
    traces[node_name] = trace
    return {"node_traces": traces}


def reasoning_node(state: PosterState) -> PosterState:
    started_at = _utc_now_iso()
    started_mono = time.monotonic()
    raw = state.get("raw_wod", {})
    movements = raw.get("movements", []) if isinstance(raw, dict) else []
    content = str(raw.get("content", ""))
    stimulus = str(raw.get("stimulus", ""))

    has_finisher = any(str(m.get("section", "")).strip().lower() == "finisher" for m in movements)
    layout = "vertical stack" if len(movements) <= 4 else "two-column masonry"
    if has_finisher:
        layout += " with right finisher sidebar"

    intensity = "fast cyclical" if "round" in content.lower() or "amrap" in content.lower() else "structured"
    if "grit" in stimulus.lower() or "power" in stimulus.lower():
        intensity = "high-intensity"

    feedback = str(state.get("feedback", "")).strip()
    strategy = (
        f"STRATEGY: {intensity}. "
        f"ARCHITECT: use {layout}. "
        f"DESIGNER: prioritize high-contrast readable typography."
    )
    if feedback:
        strategy += f" RETRY_FEEDBACK: {feedback}"
    save_prompts = bool(state.get("save_intermediate_prompts", False))
    trace = _build_node_trace(
        node_name="reasoning",
        attempt=int(state.get("retry_count", 0)) + 1,
        started_at=started_at,
        started_monotonic=started_mono,
        status="success",
        decision={
            "archetype": "amrap" if "amrap" in content.lower() else ("emom" if "emom" in content.lower() else "mixed"),
            "intensity_profile": intensity,
            "layout_strategy": "split_pane" if has_finisher else ("vertical_stack" if len(movements) <= 4 else "masonry_2col"),
            "finisher_split_required": has_finisher,
            "rationale": "derived from movement count/content/stimulus",
            "retry_feedback_applied": feedback,
        },
        prompt=_prompt_trace(
            system_prompt="ReasoningNode: derive strategy from workout tags",
            user_prompt=str(raw),
            save_text=save_prompts,
        ),
        output_ref={"strategic_intent_sha256": _sha256_text(strategy)},
    )

    update = {"strategic_intent": strategy}
    update.update(_with_node_trace(state, "reasoning", trace))
    return update


def editor_node(state: PosterState) -> PosterState:
    started_at = _utc_now_iso()
    started_mono = time.monotonic()
    raw = state.get("raw_wod", {})
    try:
        validated = validate_workout_schema(raw)
    except ToolExecutionError as exc:
        trace = _build_node_trace(
            node_name="editor",
            attempt=int(state.get("retry_count", 0)) + 1,
            started_at=started_at,
            started_monotonic=started_mono,
            status="failed",
            decision={
                "schema_valid": False,
                "movement_rows_validated": 0,
                "contiguity_check_passed": False,
                "normalizations_applied": [],
                "hard_fail": True,
                "hard_fail_reason": str(exc),
            },
            prompt=_prompt_trace(
                system_prompt="EditorNode: validate workout schema",
                user_prompt=str(raw),
                save_text=bool(state.get("save_intermediate_prompts", False)),
            ),
            tools=[{"name": "validate_workout_schema", "status": "failed", "duration_ms": 0, "error": str(exc)}],
            errors=[str(exc)],
        )
        update = {
            "is_valid": False,
            "feedback": str(exc),
            "error_log": [*state.get("error_log", []), f"editor: {exc}"],
        }
        update.update(_with_node_trace(state, "editor", trace))
        return update

    trace = _build_node_trace(
        node_name="editor",
        attempt=int(state.get("retry_count", 0)) + 1,
        started_at=started_at,
        started_monotonic=started_mono,
        status="success",
        decision={
            "schema_valid": True,
            "movement_rows_validated": len(validated.get("movements", [])),
            "contiguity_check_passed": True,
            "normalizations_applied": ["pydantic_type_validation", "string_strip"],
            "hard_fail": False,
        },
        prompt=_prompt_trace(
            system_prompt="EditorNode: validate workout schema",
            user_prompt=str(raw),
            save_text=bool(state.get("save_intermediate_prompts", False)),
        ),
        tools=[{"name": "validate_workout_schema", "status": "success", "duration_ms": 0, "error": ""}],
        output_ref={"validated_wod_sha256": _sha256_text(str(validated))},
    )
    update = {"validated_wod": validated}
    update.update(_with_node_trace(state, "editor", trace))
    return update


def architect_node(state: PosterState) -> PosterState:
    started_at = _utc_now_iso()
    started_mono = time.monotonic()
    validated = state.get("validated_wod")
    if not validated:
        err = "architect received empty validated_wod"
        trace = _build_node_trace(
            node_name="architect",
            attempt=int(state.get("retry_count", 0)) + 1,
            started_at=started_at,
            started_monotonic=started_mono,
            status="failed",
            decision={"hard_fail": True, "overflow_detected": False},
            prompt=_prompt_trace(
                system_prompt="ArchitectNode: generate coordinate map",
                user_prompt="",
                save_text=bool(state.get("save_intermediate_prompts", False)),
            ),
            tools=[{"name": "generate_coordinate_map", "status": "failed", "duration_ms": 0, "error": err}],
            errors=[err],
        )
        update = {
            "is_valid": False,
            "feedback": err,
            "error_log": [*state.get("error_log", []), "architect: missing validated_wod"],
        }
        update.update(_with_node_trace(state, "architect", trace))
        return update
    try:
        coordinates = generate_coordinate_map(validated)
    except ToolExecutionError as exc:
        trace = _build_node_trace(
            node_name="architect",
            attempt=int(state.get("retry_count", 0)) + 1,
            started_at=started_at,
            started_monotonic=started_mono,
            status="failed",
            decision={"hard_fail": True, "overflow_detected": True},
            prompt=_prompt_trace(
                system_prompt="ArchitectNode: generate coordinate map",
                user_prompt=str(validated),
                save_text=bool(state.get("save_intermediate_prompts", False)),
            ),
            tools=[{"name": "generate_coordinate_map", "status": "failed", "duration_ms": 0, "error": str(exc)}],
            errors=[str(exc)],
        )
        update = {
            "is_valid": False,
            "feedback": str(exc),
            "error_log": [*state.get("error_log", []), f"architect: {exc}"],
        }
        update.update(_with_node_trace(state, "architect", trace))
        return update

    zones = coordinates.get("zones", {})
    sidebar = zones.get("sidebar") if isinstance(zones, dict) else None
    trace = _build_node_trace(
        node_name="architect",
        attempt=int(state.get("retry_count", 0)) + 1,
        started_at=started_at,
        started_monotonic=started_mono,
        status="success",
        decision={
            "canvas_width": coordinates.get("canvas", {}).get("width", 1024),
            "canvas_height": coordinates.get("canvas", {}).get("height", 1024),
            "sidebar_reserved": bool(sidebar),
            "sidebar_width_px": int(sidebar.get("width", 0)) if sidebar else 0,
            "zone_header": zones.get("header"),
            "zone_body": zones.get("body"),
            "zone_footer": zones.get("footer"),
            "movement_cluster_count": len(coordinates.get("movement_boxes", [])),
            "overflow_detected": False,
            "hard_fail": False,
        },
        prompt=_prompt_trace(
            system_prompt="ArchitectNode: generate coordinate map",
            user_prompt=str(validated),
            save_text=bool(state.get("save_intermediate_prompts", False)),
        ),
        tools=[{"name": "generate_coordinate_map", "status": "success", "duration_ms": 0, "error": ""}],
        output_ref={"layout_coordinates_sha256": _sha256_text(str(coordinates))},
    )
    update = {"layout_coordinates": coordinates}
    update.update(_with_node_trace(state, "architect", trace))
    return update


def designer_node(state: PosterState) -> PosterState:
    started_at = _utc_now_iso()
    started_mono = time.monotonic()
    validated = state.get("validated_wod")
    if not validated:
        err = "designer received empty validated_wod"
        trace = _build_node_trace(
            node_name="designer",
            attempt=int(state.get("retry_count", 0)) + 1,
            started_at=started_at,
            started_monotonic=started_mono,
            status="failed",
            decision={"brand_profile": "", "negative_prompt_applied": False},
            prompt=_prompt_trace(
                system_prompt="DesignerNode: build final graphic prompt",
                user_prompt="",
                save_text=bool(state.get("save_intermediate_prompts", False)),
            ),
            errors=[err],
        )
        update = {
            "is_valid": False,
            "feedback": err,
            "error_log": [*state.get("error_log", []), "designer: missing validated_wod"],
        }
        update.update(_with_node_trace(state, "designer", trace))
        return update

    assets = get_brand_assets(str(validated.get("stimulus", "")))
    workout = WorkoutRecord.from_dict(validated)
    base_prompt = build_image_prompt(workout)

    layout = state.get("layout_coordinates", {})
    strategy = state.get("strategic_intent", "")

    design_appendix = (
        "\n\n---\n\n"
        "Technical Layout Manifest:\n"
        f"{strategy}\n"
        f"Canvas: {layout.get('canvas')}\n"
        f"Safe Zone: {layout.get('safe_zone')}px\n"
        f"Movement Boxes: {layout.get('movement_boxes')}\n"
        f"Brand Assets: {assets}\n"
        "NEGATIVE_PROMPT: low-resolution text, illegible characters, spelling errors, mismatched rep counts, "
        "overlapping text blocks, text touching borders, distorted limbs, multiple heads, floating equipment, "
        "cursive fonts, handwriting style, messy backgrounds, busy textures, low contrast, gradients that obscure text, "
        "duplicate athletes in a single frame without progression arrows, watermark, signature."
    )

    final_prompt = base_prompt + design_appendix
    trace = _build_node_trace(
        node_name="designer",
        attempt=int(state.get("retry_count", 0)) + 1,
        started_at=started_at,
        started_monotonic=started_mono,
        status="success",
        decision={
            "brand_profile": assets.get("mood", ""),
            "palette": {"accent_hex": assets.get("palette", {}).get("accent", "")},
            "lighting_profile": assets.get("lighting", ""),
            "negative_prompt_applied": True,
            "final_prompt_sections": [
                "base_prompt",
                "technical_layout_manifest",
                "negative_prompt",
            ],
            "final_prompt_char_count": len(final_prompt),
            "final_prompt_sha256": _sha256_text(final_prompt),
        },
        prompt=_prompt_trace(
            system_prompt="DesignerNode: apply brand assets and constraints",
            user_prompt=str({"strategy": strategy, "layout": layout, "assets": assets}),
            save_text=bool(state.get("save_intermediate_prompts", False)),
        ),
        tools=[{"name": "get_brand_assets", "status": "success", "duration_ms": 0, "error": ""}],
        output_ref={"final_prompt_sha256": _sha256_text(final_prompt)},
    )
    update = {
        "brand_assets": assets,
        "final_graphic_prompt": final_prompt,
    }
    update.update(_with_node_trace(state, "designer", trace))
    return update


def generator_node(state: PosterState) -> PosterState:
    started_at = _utc_now_iso()
    started_mono = time.monotonic()
    prompt = state.get("final_graphic_prompt", "")
    if not prompt:
        err = "generator received empty prompt"
        trace = _build_node_trace(
            node_name="generator",
            attempt=int(state.get("retry_count", 0)) + 1,
            started_at=started_at,
            started_monotonic=started_mono,
            status="failed",
            decision={"image_written": False, "quality_gate_passed": False, "failure_category": "missing_prompt"},
            prompt=_prompt_trace(
                system_prompt="GeneratorNode: call image model",
                user_prompt="",
                save_text=bool(state.get("save_intermediate_prompts", False)),
            ),
            errors=[err],
        )
        update = {
            "is_valid": False,
            "feedback": err,
            "error_log": [*state.get("error_log", []), "generator: missing prompt"],
        }
        update.update(_with_node_trace(state, "generator", trace))
        return update

    output_path = Path(state["output_path"])
    try:
        metrics = generate_gemini_image(
            prompt=prompt,
            output_path=output_path,
            api_key=state["api_key"],
            model=state["model"],
            aspect_ratio=state["aspect_ratio"],
            max_retries=state["max_retries_api"],
            max_retry_delay_seconds=state["max_retry_delay_seconds"],
            retry_jitter_ratio=state["retry_jitter_ratio"],
        )
    except Exception as exc:
        trace = _build_node_trace(
            node_name="generator",
            attempt=int(state.get("retry_count", 0)) + 1,
            started_at=started_at,
            started_monotonic=started_mono,
            status="failed",
            decision={
                "model": state.get("model", ""),
                "api_call_count": 1,
                "api_retry_count": state.get("max_retries_api", 0),
                "image_written": False,
                "quality_gate_passed": False,
                "failure_category": "generator_exception",
            },
            prompt=_prompt_trace(
                system_prompt="GeneratorNode: call image model",
                user_prompt=prompt,
                save_text=bool(state.get("save_intermediate_prompts", False)),
            ),
            errors=[str(exc)],
        )
        update = {
            "is_valid": False,
            "feedback": str(exc),
            "error_log": [*state.get("error_log", []), f"generator: {exc}"],
        }
        update.update(_with_node_trace(state, "generator", trace))
        return update

    trace = _build_node_trace(
        node_name="generator",
        attempt=int(state.get("retry_count", 0)) + 1,
        started_at=started_at,
        started_monotonic=started_mono,
        status="success",
        decision={
            "model": state.get("model", ""),
            "api_call_count": 1,
            "api_retry_count": state.get("max_retries_api", 0),
            "image_written": True,
            "image_width": int((metrics or {}).get("image_width", 0)),
            "image_height": int((metrics or {}).get("image_height", 0)),
            "image_bytes": int((metrics or {}).get("image_bytes", 0)),
            "quality_gate_passed": True,
        },
        prompt=_prompt_trace(
            system_prompt="GeneratorNode: call image model",
            user_prompt=prompt,
            save_text=bool(state.get("save_intermediate_prompts", False)),
        ),
        artifacts=[str(output_path)],
    )

    update = {
        "image_path": str(output_path),
        "image_metrics": metrics,
    }
    update.update(_with_node_trace(state, "generator", trace))
    return update


def validation_node(state: PosterState) -> PosterState:
    started_at = _utc_now_iso()
    started_mono = time.monotonic()
    validated = state.get("validated_wod", {})
    movements = validated.get("movements", []) if isinstance(validated, dict) else []
    image_path = state.get("image_path", "")

    if not image_path:
        err = "validation received empty image path"
        trace = _build_node_trace(
            node_name="validator",
            attempt=int(state.get("retry_count", 0)) + 1,
            started_at=started_at,
            started_monotonic=started_mono,
            status="failed",
            decision={
                "method": "ocr_compare",
                "expected_tokens_count": 0,
                "matched_tokens_count": 0,
                "mismatches": [err],
                "similarity_score": 0.0,
                "threshold": 1.0,
                "is_valid": False,
                "retry_requested": True,
                "retry_reason": err,
            },
            prompt=_prompt_trace(
                system_prompt="ValidatorNode: verify OCR text against expected workout tokens",
                user_prompt="",
                save_text=bool(state.get("save_intermediate_prompts", False)),
            ),
            errors=[err],
        )
        update = {
            "is_valid": False,
            "feedback": err,
            "retry_count": state.get("retry_count", 0) + 1,
            "error_log": [*state.get("error_log", []), "validator: missing image path"],
        }
        history = [*state.get("retry_history", []), {"attempt": int(state.get("retry_count", 0)) + 1, "reason": err, "timestamp_utc": _utc_now_iso()}]
        update["retry_history"] = history
        update.update(_with_node_trace(state, "validator", trace))
        return update

    expected_rows = [
        {
            "name": str(m.get("name", "")),
            "reps": str(m.get("reps", "")),
            "rx_weight": str(m.get("rx_weight", "")),
        }
        for m in movements
    ]

    try:
        audit = verify_image_accuracy(str(image_path), expected_rows)
    except ToolExecutionError as exc:
        trace = _build_node_trace(
            node_name="validator",
            attempt=int(state.get("retry_count", 0)) + 1,
            started_at=started_at,
            started_monotonic=started_mono,
            status="failed",
            decision={
                "method": "ocr_compare",
                "expected_tokens_count": len(expected_rows),
                "matched_tokens_count": 0,
                "mismatches": [str(exc)],
                "similarity_score": 0.0,
                "threshold": 1.0,
                "is_valid": False,
                "retry_requested": True,
                "retry_reason": str(exc),
            },
            prompt=_prompt_trace(
                system_prompt="ValidatorNode: verify OCR text against expected workout tokens",
                user_prompt=str(expected_rows),
                save_text=bool(state.get("save_intermediate_prompts", False)),
            ),
            tools=[{"name": "verify_image_accuracy", "status": "failed", "duration_ms": 0, "error": str(exc)}],
            errors=[str(exc)],
        )
        update = {
            "validation_result": {
                "is_valid": False,
                "similarity_score": 0.0,
                "mismatches": [str(exc)],
            },
            "similarity_score": 0.0,
            "is_valid": False,
            "feedback": str(exc),
            "retry_count": state.get("retry_count", 0) + 1,
            "error_log": [*state.get("error_log", []), f"validator: {exc}"],
        }
        history = [*state.get("retry_history", []), {"attempt": int(state.get("retry_count", 0)) + 1, "reason": str(exc), "timestamp_utc": _utc_now_iso()}]
        update["retry_history"] = history
        update.update(_with_node_trace(state, "validator", trace))
        return update

    expected_tokens_count = len([1 for row in expected_rows if row.get("name") and row.get("reps")]) + len([1 for row in expected_rows if row.get("rx_weight")])
    mismatches = list(audit.get("mismatches", []))
    matched_tokens = max(0, expected_tokens_count - len(mismatches))
    is_valid = bool(audit.get("is_valid", False))
    similarity_score = float(audit.get("similarity_score", 0.0))
    retry_requested = not is_valid
    retry_reason = f"validation mismatches: {mismatches}" if retry_requested else ""

    trace = _build_node_trace(
        node_name="validator",
        attempt=int(state.get("retry_count", 0)) + 1,
        started_at=started_at,
        started_monotonic=started_mono,
        status="success" if is_valid else "failed",
        decision={
            "method": "ocr_compare",
            "expected_tokens_count": expected_tokens_count,
            "matched_tokens_count": matched_tokens,
            "mismatches": mismatches,
            "similarity_score": similarity_score,
            "threshold": 1.0,
            "is_valid": is_valid,
            "retry_requested": retry_requested,
            "retry_reason": retry_reason,
        },
        prompt=_prompt_trace(
            system_prompt="ValidatorNode: verify OCR text against expected workout tokens",
            user_prompt=str(expected_rows),
            save_text=bool(state.get("save_intermediate_prompts", False)),
        ),
        tools=[{"name": "verify_image_accuracy", "status": "success", "duration_ms": 0, "error": ""}],
    )

    update = {
        "validation_result": audit,
        "similarity_score": similarity_score,
        "is_valid": is_valid,
        "feedback": "" if is_valid else retry_reason,
        "retry_count": state.get("retry_count", 0) if is_valid else state.get("retry_count", 0) + 1,
    }
    if retry_requested:
        history = [*state.get("retry_history", []), {"attempt": int(state.get("retry_count", 0)) + 1, "reason": retry_reason, "timestamp_utc": _utc_now_iso()}]
        update["retry_history"] = history
    update.update(_with_node_trace(state, "validator", trace))
    return update


def should_retry(state: PosterState) -> str:
    if state.get("is_valid"):
        return "success"
    if int(state.get("retry_count", 0)) >= int(state.get("max_retries", 3)):
        return "fail"
    return "retry"

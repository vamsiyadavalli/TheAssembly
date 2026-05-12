from __future__ import annotations

from pathlib import Path
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


def reasoning_node(state: PosterState) -> PosterState:
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

    return {"strategic_intent": strategy}


def editor_node(state: PosterState) -> PosterState:
    raw = state.get("raw_wod", {})
    try:
        validated = validate_workout_schema(raw)
    except ToolExecutionError as exc:
        return {
            "is_valid": False,
            "feedback": str(exc),
            "error_log": [*state.get("error_log", []), f"editor: {exc}"],
        }
    return {"validated_wod": validated}


def architect_node(state: PosterState) -> PosterState:
    validated = state.get("validated_wod")
    if not validated:
        return {
            "is_valid": False,
            "feedback": "architect received empty validated_wod",
            "error_log": [*state.get("error_log", []), "architect: missing validated_wod"],
        }
    try:
        coordinates = generate_coordinate_map(validated)
    except ToolExecutionError as exc:
        return {
            "is_valid": False,
            "feedback": str(exc),
            "error_log": [*state.get("error_log", []), f"architect: {exc}"],
        }
    return {"layout_coordinates": coordinates}


def designer_node(state: PosterState) -> PosterState:
    validated = state.get("validated_wod")
    if not validated:
        return {
            "is_valid": False,
            "feedback": "designer received empty validated_wod",
            "error_log": [*state.get("error_log", []), "designer: missing validated_wod"],
        }

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

    return {
        "brand_assets": assets,
        "final_graphic_prompt": base_prompt + design_appendix,
    }


def generator_node(state: PosterState) -> PosterState:
    prompt = state.get("final_graphic_prompt", "")
    if not prompt:
        return {
            "is_valid": False,
            "feedback": "generator received empty prompt",
            "error_log": [*state.get("error_log", []), "generator: missing prompt"],
        }

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
        return {
            "is_valid": False,
            "feedback": str(exc),
            "error_log": [*state.get("error_log", []), f"generator: {exc}"],
        }

    return {
        "image_path": str(output_path),
        "image_metrics": metrics,
    }


def validation_node(state: PosterState) -> PosterState:
    validated = state.get("validated_wod", {})
    movements = validated.get("movements", []) if isinstance(validated, dict) else []
    image_path = state.get("image_path", "")

    if not image_path:
        return {
            "is_valid": False,
            "feedback": "validation received empty image path",
            "retry_count": state.get("retry_count", 0) + 1,
            "error_log": [*state.get("error_log", []), "validator: missing image path"],
        }

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
        return {
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

    return {
        "validation_result": audit,
        "similarity_score": float(audit.get("similarity_score", 0.0)),
        "is_valid": bool(audit.get("is_valid", False)),
        "feedback": "" if audit.get("is_valid") else f"validation mismatches: {audit.get('mismatches', [])}",
        "retry_count": state.get("retry_count", 0) if audit.get("is_valid") else state.get("retry_count", 0) + 1,
    }


def should_retry(state: PosterState) -> str:
    if state.get("is_valid"):
        return "success"
    if int(state.get("retry_count", 0)) >= int(state.get("max_retries", 3)):
        return "fail"
    return "retry"

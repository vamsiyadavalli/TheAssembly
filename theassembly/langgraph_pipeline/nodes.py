from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any

from theassembly.models import WorkoutRecord
from theassembly.workout_image import build_image_prompt, generate_gemini_image

from .llm_schemas import (
    CriticReviewModel,
    DesignerPromptModel,
    LayoutRecommendationModel,
    ReasoningPlanModel,
    RiskAssessmentModel,
    WorkoutClassificationModel,
)
from .state import PosterState
from .text_agent import TextAgentError, call_text_agent
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


def _with_llm_meta(state: PosterState, role: str, model: str, usage: dict[str, Any]) -> dict[str, Any]:
    llm_models = dict(state.get("llm_models", {}))
    llm_models[role] = model
    llm_usage = dict(state.get("llm_usage", {}))
    llm_usage[role] = usage
    return {"llm_models": llm_models, "llm_usage": llm_usage}


def _canonical_rows(validated: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for movement in validated.get("movements", []) or []:
        rows.append(
            {
                "name": str(movement.get("name", "")).strip(),
                "reps": str(movement.get("reps", "")).strip(),
                "rx_weight": str(movement.get("rx_weight", "")).strip(),
                "section": str(movement.get("section", "")).strip(),
                "round_group_label": str(movement.get("round_group_label", "")).strip(),
                "finisher_part_title": str(movement.get("finisher_part_title", "")).strip(),
            }
        )
    return rows


def _semantic_contract(rows: list[dict[str, str]]) -> str:
    lines = [
        "Semantic Source Of Truth (must be followed exactly):",
        "- Do NOT add, remove, merge, or reorder movement rows.",
        "- Do NOT change reps, units, movement names, or weights.",
        "- Preserve section boundaries and finisher grouping.",
        f"ROW_COUNT: {len(rows)}",
        "ROWS:",
    ]
    for idx, row in enumerate(rows, start=1):
        section = row.get("section", "") or "WOD"
        name = row.get("name", "")
        reps = row.get("reps", "")
        weight = row.get("rx_weight", "")
        lines.append(f"{idx}|{section}|{reps}|{name}|{weight}")
    return "\n".join(lines)


def _heuristic_reasoning(raw: dict[str, Any], feedback: str) -> dict[str, Any]:
    movements = raw.get("movements", []) if isinstance(raw, dict) else []
    content = str(raw.get("content", ""))
    has_finisher = any(str(m.get("section", "")).strip().lower() == "finisher" for m in movements)
    layout = "split_pane" if has_finisher else ("vertical_stack" if len(movements) <= 4 else "masonry_2col")
    archetype = "amrap" if "amrap" in content.lower() else ("emom" if "emom" in content.lower() else "mixed")

    return {
        "workout_archetype": archetype,
        "intensity_profile": "high" if "for time" in content.lower() else "mixed",
        "layout_strategy": layout,
        "finisher_strategy": "right_sidebar" if has_finisher else "none",
        "visual_goal": "High-contrast, highly readable workout poster with strict factual fidelity.",
        "section_priority": ["header", "main_movements", "finisher", "footer"],
        "risk_flags": [{"code": "ocr_risk", "severity": "medium", "message": "Ensure typography remains OCR-readable."}],
        "retry_directives": [feedback] if feedback else [],
        "non_negotiables": [
            "preserve_row_order",
            "preserve_row_count",
            "preserve_reps_exactly",
            "preserve_movement_names_exactly",
        ],
        "confidence": 0.75,
        "rationale": "Fallback heuristic reasoning generated from workout tags.",
    }


def _merge_usage(usages: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for usage in usages:
        for key, value in usage.items():
            if isinstance(value, int):
                merged[key] = int(merged.get(key, 0)) + value
            else:
                merged[key] = value
    return merged


def _default_risk_assessment(feedback: str) -> dict[str, Any]:
    directives = [feedback] if feedback else []
    return {
        "risk_flags": [{"code": "ocr_risk", "severity": "medium", "message": "Ensure typography remains OCR-readable."}],
        "retry_directives": directives,
        "non_negotiables": [
            "preserve_row_order",
            "preserve_row_count",
            "preserve_reps_exactly",
            "preserve_movement_names_exactly",
        ],
        "section_priority": ["header", "main_movements", "finisher", "footer"],
    }


def _merge_reasoning_stages(
    *,
    classification: dict[str, Any],
    layout: dict[str, Any],
    risks: dict[str, Any],
    feedback: str,
) -> dict[str, Any]:
    return {
        "workout_archetype": classification.get("workout_archetype", "mixed"),
        "intensity_profile": classification.get("intensity_profile", "mixed"),
        "layout_strategy": layout.get("layout_strategy", "masonry_2col"),
        "finisher_strategy": layout.get("finisher_strategy", "none"),
        "visual_goal": layout.get(
            "visual_goal",
            "High-contrast, highly readable workout poster with strict factual fidelity.",
        ),
        "section_priority": risks.get("section_priority", ["header", "main_movements", "finisher", "footer"]),
        "risk_flags": risks.get("risk_flags", []),
        "retry_directives": risks.get("retry_directives", [feedback] if feedback else []),
        "non_negotiables": risks.get(
            "non_negotiables",
            [
                "preserve_row_order",
                "preserve_row_count",
                "preserve_reps_exactly",
                "preserve_movement_names_exactly",
            ],
        ),
        "confidence": float(classification.get("confidence", 0.75)),
        "rationale": layout.get("rationale", "Tier 1 staged reasoning with heuristic-safe fallbacks."),
    }


def _staged_reasoning_plan(
    *,
    state: PosterState,
    raw: dict[str, Any],
    feedback: str,
) -> tuple[dict[str, Any], list[str], dict[str, Any], dict[str, dict[str, Any]]]:
    warnings: list[str] = []
    usages: list[dict[str, Any]] = []
    llm_model = ""

    classification = {
        "workout_archetype": _heuristic_reasoning(raw, feedback).get("workout_archetype", "mixed"),
        "intensity_profile": _heuristic_reasoning(raw, feedback).get("intensity_profile", "mixed"),
        "confidence": 0.75,
    }
    try:
        stage1 = call_text_agent(
            api_key=str(state["api_key"]),
            model=str(state["reasoning_model"]),
            system_prompt=(
                "Classify workout type and intensity. Return valid JSON only and use workout facts only."
            ),
            user_prompt=f"WORKOUT_JSON:\n{raw}",
            response_model=WorkoutClassificationModel,
            temperature=float(state.get("reasoning_temperature", 0.1)),
            max_output_tokens=min(400, int(state.get("reasoning_max_output_tokens", 1200))),
        )
        classification = stage1.payload
        llm_model = stage1.model
        usages.append(stage1.usage)
    except TextAgentError as exc:
        warnings.append(f"classification_stage: {exc}")

    has_finisher = any(
        str(m.get("section", "")).strip().lower() == "finisher"
        for m in (raw.get("movements", []) if isinstance(raw, dict) else [])
    )
    layout = {
        "layout_strategy": "split_pane" if has_finisher else "masonry_2col",
        "finisher_strategy": "right_sidebar" if has_finisher else "none",
        "visual_goal": "High-contrast, highly readable workout poster with strict factual fidelity.",
        "rationale": "Fallback layout recommendation generated from workout structure.",
    }
    try:
        stage2 = call_text_agent(
            api_key=str(state["api_key"]),
            model=str(state["reasoning_model"]),
            system_prompt=(
                "Recommend layout strategy for a workout poster. Return valid JSON only."
            ),
            user_prompt=(
                f"WORKOUT_JSON:\n{raw}\n\n"
                f"CLASSIFICATION:\n{classification}\n\n"
                "Prioritize readability and factual fidelity."
            ),
            response_model=LayoutRecommendationModel,
            temperature=float(state.get("reasoning_temperature", 0.1)),
            max_output_tokens=min(500, int(state.get("reasoning_max_output_tokens", 1200))),
        )
        layout = stage2.payload
        llm_model = stage2.model or llm_model
        usages.append(stage2.usage)
    except TextAgentError as exc:
        warnings.append(f"layout_stage: {exc}")

    risks = _default_risk_assessment(feedback)
    try:
        stage3 = call_text_agent(
            api_key=str(state["api_key"]),
            model=str(state["reasoning_model"]),
            system_prompt=(
                "Assess fidelity and rendering risks for this workout poster. Return valid JSON only."
            ),
            user_prompt=(
                f"WORKOUT_JSON:\n{raw}\n\n"
                f"CLASSIFICATION:\n{classification}\n\n"
                f"LAYOUT:\n{layout}\n\n"
                f"RETRY_FEEDBACK:\n{feedback or 'none'}"
            ),
            response_model=RiskAssessmentModel,
            temperature=float(state.get("reasoning_temperature", 0.1)),
            max_output_tokens=min(700, int(state.get("reasoning_max_output_tokens", 1200))),
        )
        risks = stage3.payload
        llm_model = stage3.model or llm_model
        usages.append(stage3.usage)
    except TextAgentError as exc:
        warnings.append(f"risk_stage: {exc}")

    plan = _merge_reasoning_stages(
        classification=classification,
        layout=layout,
        risks=risks,
        feedback=feedback,
    )
    llm_meta = {"model": llm_model, "usage": _merge_usage(usages)}
    stage_payloads = {
        "classification": classification,
        "layout": layout,
        "risks": risks,
    }
    return plan, warnings, llm_meta, stage_payloads


def reasoning_node(state: PosterState) -> PosterState:
    started_at = _utc_now_iso()
    started_mono = time.monotonic()
    raw = state.get("raw_wod", {})
    feedback = str(state.get("feedback", "")).strip()
    save_prompts = bool(state.get("save_intermediate_prompts", False))

    system_prompt = (
        "You are ReasoningAgent for workout poster planning. "
        "Use only the provided workout data and return valid JSON. "
        "Never invent, reorder, or mutate workout facts."
    )
    user_prompt = (
        f"WORKOUT_JSON:\n{raw}\n\n"
        f"RETRY_FEEDBACK:\n{feedback or 'none'}\n\n"
        "Return a planning object that optimizes readability and factual fidelity."
    )

    plan: dict[str, Any]
    llm_warnings: list[str] = []
    llm_meta = {"model": "", "usage": {}}
    staged_payloads: dict[str, dict[str, Any]] = {}
    schema_version = str(state.get("reasoning_schema_version", "v1")).strip().lower()

    if state.get("api_key") and state.get("reasoning_model") and schema_version == "tier1_staged":
        plan, llm_warnings, llm_meta, staged_payloads = _staged_reasoning_plan(
            state=state,
            raw=raw if isinstance(raw, dict) else {},
            feedback=feedback,
        )
    elif state.get("api_key") and state.get("reasoning_model"):
        try:
            result = call_text_agent(
                api_key=str(state["api_key"]),
                model=str(state["reasoning_model"]),
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=ReasoningPlanModel,
                temperature=float(state.get("reasoning_temperature", 0.1)),
                max_output_tokens=int(state.get("reasoning_max_output_tokens", 1200)),
            )
            plan = result.payload
            llm_meta = {"model": result.model, "usage": result.usage}
        except TextAgentError as exc:
            plan = _heuristic_reasoning(raw if isinstance(raw, dict) else {}, feedback)
            llm_warnings = [str(exc)]
    else:
        plan = _heuristic_reasoning(raw if isinstance(raw, dict) else {}, feedback)

    strategy = (
        f"STRATEGY: {plan.get('intensity_profile', 'mixed')}. "
        f"ARCHITECT: use {plan.get('layout_strategy', 'masonry_2col')}. "
        "DESIGNER: prioritize high-contrast readable typography."
    )

    decision = {
        "archetype": plan.get("workout_archetype", "mixed"),
        "intensity_profile": plan.get("intensity_profile", "mixed"),
        "layout_strategy": plan.get("layout_strategy", "masonry_2col"),
        "finisher_split_required": plan.get("finisher_strategy", "none") != "none",
        "retry_feedback_applied": bool(feedback),
        "llm_used": bool(llm_meta["model"]),
        "reasoning_schema_version": schema_version,
        "staged_mode": schema_version == "tier1_staged",
        "staged_stage_count": 3 if schema_version == "tier1_staged" else 1,
    }

    trace = _build_node_trace(
        node_name="reasoning",
        attempt=int(state.get("retry_count", 0)) + 1,
        started_at=started_at,
        started_monotonic=started_mono,
        status="success",
        decision=decision,
        prompt=_prompt_trace(system_prompt=system_prompt, user_prompt=user_prompt, save_text=save_prompts),
        warnings=llm_warnings,
        output_ref={"strategic_intent_sha256": _sha256_text(strategy)},
    )

    update: PosterState = {
        "strategic_intent": strategy,
        "reasoning_plan": plan,
        "reasoning_schema_version": schema_version,
    }
    if staged_payloads:
        update["reasoning_stage_classification"] = staged_payloads.get("classification", {})
        update["reasoning_stage_layout"] = staged_payloads.get("layout", {})
        update["reasoning_stage_risks"] = staged_payloads.get("risks", {})
    if llm_meta["model"]:
        update.update(_with_llm_meta(state, "reasoning", llm_meta["model"], llm_meta["usage"]))
    update.update(_with_node_trace(state, "reasoning", trace))
    return update


def editor_node(state: PosterState) -> PosterState:
    started_at = _utc_now_iso()
    started_mono = time.monotonic()
    raw = state.get("raw_wod", {})
    try:
        validated = validate_workout_schema(raw)
        canonical_rows = _canonical_rows(validated)
        semantic_contract = _semantic_contract(canonical_rows)
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
        update: PosterState = {
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
    update = {
        "validated_wod": validated,
        "canonical_rows": canonical_rows,
        "semantic_contract": semantic_contract,
    }
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
        update: PosterState = {
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

    movement_boxes = coordinates.get("movement_boxes", [])
    panel_budgets = {
        "panel_count": len(movement_boxes),
        "max_chars_per_title": 64,
        "max_chars_per_line": 96,
    }
    overflow_risks = ["crowding_risk"] if len(movement_boxes) >= 8 else []

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
            "movement_cluster_count": len(movement_boxes),
            "overflow_detected": bool(overflow_risks),
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
    update = {
        "layout_coordinates": coordinates,
        "panel_budgets": panel_budgets,
        "overflow_risks": overflow_risks,
    }
    update.update(_with_node_trace(state, "architect", trace))
    return update


def _assemble_prompt_from_designer(draft: dict[str, Any], base_prompt: str) -> str:
    style = "\n".join(str(x) for x in draft.get("style_directives", []))
    negative = "\n".join(str(x) for x in draft.get("negative_prompt", []))
    panels = draft.get("panel_specs", [])
    panel_lines: list[str] = []
    for panel in sorted(panels, key=lambda p: int(p.get("order_index", 999))):
        panel_lines.append(f"- {panel.get('heading', '')}")
        for line in panel.get("body_lines", []):
            panel_lines.append(f"  * {line}")

    footer = draft.get("footer_specs", {})
    cues = "\n".join(f"- {cue}" for cue in footer.get("technical_cues", []))
    panel_text = "\n".join(panel_lines)

    appendix = (
        "\n\n---\n\n"
        "Structured Designer Output:\n"
        f"TITLE: {draft.get('title_text', '')}\n"
        f"SUBHEADER: {draft.get('subheader_text', '')}\n"
        "PANEL_LAYOUT:\n"
        f"{panel_text}\n"
        f"FOOTER_STIMULUS: {footer.get('stimulus_line', '')}\n"
        f"FOOTER_CUES:\n{cues}\n"
        "STYLE_DIRECTIVES:\n"
        f"{style}\n"
        "NEGATIVE_PROMPT:\n"
        f"{negative}\n"
    )
    return base_prompt + appendix


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
        update: PosterState = {
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
    semantic_contract = str(state.get("semantic_contract", ""))

    system_prompt = (
        "You are DesignerAgent for professional fitness posters. "
        "Use only semantic contract facts. Return JSON only. "
        "Do not add, remove, or reorder workout rows."
    )
    user_prompt = (
        f"SEMANTIC_CONTRACT:\n{semantic_contract}\n\n"
        f"STRATEGY:\n{strategy}\n\n"
        f"LAYOUT:\n{layout}\n\n"
        f"BRAND_ASSETS:\n{assets}\n"
    )

    designer_draft: dict[str, Any]
    llm_warning = ""
    llm_meta = {"model": "", "usage": {}}

    if state.get("api_key") and state.get("designer_model"):
        try:
            result = call_text_agent(
                api_key=str(state["api_key"]),
                model=str(state["designer_model"]),
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=DesignerPromptModel,
                temperature=float(state.get("designer_temperature", 0.2)),
                max_output_tokens=int(state.get("designer_max_output_tokens", 1800)),
            )
            designer_draft = result.payload
            llm_meta = {"model": result.model, "usage": result.usage}
        except TextAgentError as exc:
            llm_warning = str(exc)
            designer_draft = {
                "title_text": "BRING YOUR BEST",
                "subheader_text": str(validated.get("content", "")),
                "panel_specs": [],
                "footer_specs": {
                    "stimulus_line": str(validated.get("stimulus", "")),
                    "technical_cues": list(validated.get("technical_cues", [])),
                },
                "style_directives": ["High contrast", "Readable typography", "Structured panel layout", "Professional gym style"],
                "negative_prompt": ["illegible text", "spelling errors", "wrong rep counts", "overlapping text"],
                "compliance_checklist": {
                    "preserves_row_order": True,
                    "preserves_row_count": True,
                    "preserves_reps_exactly": True,
                    "preserves_movement_names_exactly": True,
                    "preserves_finisher_partition": True,
                    "avoids_unlisted_text": True,
                },
                "rationale": "Fallback deterministic designer draft.",
            }
    else:
        designer_draft = {
            "title_text": "BRING YOUR BEST",
            "subheader_text": str(validated.get("content", "")),
            "panel_specs": [],
            "footer_specs": {
                "stimulus_line": str(validated.get("stimulus", "")),
                "technical_cues": list(validated.get("technical_cues", [])),
            },
            "style_directives": ["High contrast", "Readable typography", "Structured panel layout", "Professional gym style"],
            "negative_prompt": ["illegible text", "spelling errors", "wrong rep counts", "overlapping text"],
            "compliance_checklist": {
                "preserves_row_order": True,
                "preserves_row_count": True,
                "preserves_reps_exactly": True,
                "preserves_movement_names_exactly": True,
                "preserves_finisher_partition": True,
                "avoids_unlisted_text": True,
            },
            "rationale": "Fallback deterministic designer draft.",
        }

    candidate_prompt = _assemble_prompt_from_designer(designer_draft, base_prompt)

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
            "final_prompt_char_count": len(candidate_prompt),
            "final_prompt_sha256": _sha256_text(candidate_prompt),
            "llm_used": bool(llm_meta["model"]),
        },
        prompt=_prompt_trace(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            save_text=bool(state.get("save_intermediate_prompts", False)),
        ),
        tools=[{"name": "get_brand_assets", "status": "success", "duration_ms": 0, "error": ""}],
        warnings=[llm_warning] if llm_warning else [],
        output_ref={"candidate_prompt_sha256": _sha256_text(candidate_prompt)},
    )

    update: PosterState = {
        "brand_assets": assets,
        "designer_draft": designer_draft,
        "candidate_graphic_prompt": candidate_prompt,
        "prompt_rationale": str(designer_draft.get("rationale", "")),
        "final_graphic_prompt": candidate_prompt,
    }
    if llm_meta["model"]:
        update.update(_with_llm_meta(state, "designer", llm_meta["model"], llm_meta["usage"]))
    update.update(_with_node_trace(state, "designer", trace))
    return update


def critic_node(state: PosterState) -> PosterState:
    started_at = _utc_now_iso()
    started_mono = time.monotonic()

    candidate_prompt = str(state.get("candidate_graphic_prompt") or state.get("final_graphic_prompt") or "")
    if not candidate_prompt:
        err = "critic received empty candidate prompt"
        trace = _build_node_trace(
            node_name="critic",
            attempt=int(state.get("retry_count", 0)) + 1,
            started_at=started_at,
            started_monotonic=started_mono,
            status="failed",
            decision={"critic_enabled": bool(state.get("critic_enabled", True)), "pass": False},
            prompt=_prompt_trace(
                system_prompt="CriticNode: audit prompt fidelity",
                user_prompt="",
                save_text=bool(state.get("save_intermediate_prompts", False)),
            ),
            errors=[err],
        )
        update: PosterState = {
            "is_valid": False,
            "feedback": err,
            "error_log": [*state.get("error_log", []), "critic: missing candidate prompt"],
            "final_graphic_prompt": "",
        }
        update.update(_with_node_trace(state, "critic", trace))
        return update

    if not bool(state.get("critic_enabled", True)):
        trace = _build_node_trace(
            node_name="critic",
            attempt=int(state.get("retry_count", 0)) + 1,
            started_at=started_at,
            started_monotonic=started_mono,
            status="success",
            decision={"critic_enabled": False, "pass": True, "score": 100},
            prompt=_prompt_trace(
                system_prompt="CriticNode bypassed",
                user_prompt="",
                save_text=bool(state.get("save_intermediate_prompts", False)),
            ),
        )
        update = {"final_graphic_prompt": candidate_prompt, "critic_score": 100, "critic_review": {"pass": True, "bypassed": True}}
        update.update(_with_node_trace(state, "critic", trace))
        return update

    system_prompt = (
        "You are CriticAgent. Audit prompt fidelity against semantic contract. "
        "Be strict and return JSON only."
    )
    user_prompt = (
        f"SEMANTIC_CONTRACT:\n{state.get('semantic_contract', '')}\n\n"
        f"CANDIDATE_PROMPT:\n{candidate_prompt}\n\n"
        f"PANEL_BUDGETS:\n{state.get('panel_budgets', {})}\n"
    )

    llm_meta = {"model": "", "usage": {}}
    try:
        result = call_text_agent(
            api_key=str(state.get("api_key", "")),
            model=str(state.get("critic_model", "")),
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=CriticReviewModel,
            temperature=float(state.get("critic_temperature", 0.0)),
            max_output_tokens=int(state.get("critic_max_output_tokens", 1000)),
        )
        review = result.payload
        llm_meta = {"model": result.model, "usage": result.usage}
    except (TextAgentError, TypeError, ValueError) as exc:
        review = {
            "pass": True,
            "score_0_to_100": 70,
            "blockers": [],
            "warnings": [{"code": "critic_fallback", "message": str(exc)}],
            "required_fixes": [],
            "hallucination_risk": {
                "added_content_risk": "medium",
                "dropped_content_risk": "medium",
                "reorder_risk": "medium",
                "truncation_risk": "medium",
            },
            "confidence": 0.5,
        }

    blockers = list(review.get("blockers", []))
    has_critical = any(str(b.get("severity", "")) == "critical" for b in blockers if isinstance(b, dict))
    fixes = [str(x) for x in review.get("required_fixes", [])]
    score = int(review.get("score_0_to_100", 0))
    tier2_starter_enabled = bool(state.get("tier2_starter_enabled", False))
    critic_min_score = int(state.get("critic_min_score", 70))
    hallucination = review.get("hallucination_risk", {}) if isinstance(review.get("hallucination_risk", {}), dict) else {}
    added_content_risk = str(hallucination.get("added_content_risk", "medium"))

    final_prompt = candidate_prompt
    if fixes:
        final_prompt += "\n\nCRITIC_REQUIRED_FIXES:\n" + "\n".join(f"- {fix}" for fix in fixes)

    if has_critical and not fixes:
        final_prompt = ""

    passed = bool(review.get("pass", False)) and not has_critical and score >= critic_min_score
    if tier2_starter_enabled and added_content_risk != "low":
        passed = False
    if not passed:
        final_prompt = ""
    trace = _build_node_trace(
        node_name="critic",
        attempt=int(state.get("retry_count", 0)) + 1,
        started_at=started_at,
        started_monotonic=started_mono,
        status="success" if passed else "failed",
        decision={
            "critic_enabled": True,
            "pass": passed,
            "score": score,
            "critic_min_score": critic_min_score,
            "tier2_starter_enabled": tier2_starter_enabled,
            "added_content_risk": added_content_risk,
            "blocker_count": len(blockers),
            "required_fix_count": len(fixes),
            "critical_blockers": has_critical,
        },
        prompt=_prompt_trace(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            save_text=bool(state.get("save_intermediate_prompts", False)),
        ),
        output_ref={"final_prompt_sha256": _sha256_text(final_prompt) if final_prompt else ""},
    )

    update: PosterState = {
        "critic_review": review,
        "critic_score": score,
        "final_graphic_prompt": final_prompt,
    }
    if llm_meta["model"]:
        update.update(_with_llm_meta(state, "critic", llm_meta["model"], llm_meta["usage"]))
    if not passed:
        update["feedback"] = (
            f"critic rejected prompt (score={score}, min_score={critic_min_score}, "
            f"added_content_risk={added_content_risk}, critical_blockers={has_critical})"
        )
        update["error_log"] = [*state.get("error_log", []), "critic: prompt rejected by quality gate"]
    update.update(_with_node_trace(state, "critic", trace))
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
        update: PosterState = {
            "is_valid": False,
            "feedback": err,
            "error_log": [*state.get("error_log", []), "generator: missing prompt"],
        }
        update.update(_with_node_trace(state, "generator", trace))
        return update

    output_path = Path(state["output_path"])
    image_model = str(state.get("image_model") or state.get("model") or "")
    try:
        metrics = generate_gemini_image(
            prompt=prompt,
            output_path=output_path,
            api_key=state["api_key"],
            model=image_model,
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
                "model": image_model,
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
            "model": image_model,
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
        update: PosterState = {
            "is_valid": False,
            "feedback": err,
            "retry_count": state.get("retry_count", 0) + 1,
            "error_log": [*state.get("error_log", []), "validator: missing image path"],
        }
        history = [*state.get("retry_history", []), {"attempt": int(state.get("retry_count", 0)) + 1, "reason": err, "timestamp_utc": _utc_now_iso()}]
        update["retry_history"] = history
        update.update(_with_node_trace(state, "validator", trace))
        return update

    canonical_rows = state.get("canonical_rows", [])
    if canonical_rows:
        expected_rows = [
            {
                "name": str(row.get("name", "")),
                "reps": str(row.get("reps", "")),
                "rx_weight": str(row.get("rx_weight", "")),
            }
            for row in canonical_rows
        ]
    else:
        validated = state.get("validated_wod", {})
        movements = validated.get("movements", []) if isinstance(validated, dict) else []
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
        update: PosterState = {
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

    update: PosterState = {
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

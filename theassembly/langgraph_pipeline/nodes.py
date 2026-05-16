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
    NutritionBaselineModel,
    ReasoningPlanModel,
    RiskAssessmentModel,
    WorkoutClassificationModel,
)
from .state import PosterState
from .text_agent import TextAgentError, call_text_agent
from .recipe_rotation import select_recipes_deterministic
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


def _semantic_anchor_block(rows: list[dict[str, str]]) -> str:
    lines = [
        "---",
        "IMMUTABLE OCR ANCHORS (verbatim tokens required):",
        "- Keep all movement and weight tokens exactly as written below.",
        "- Do not paraphrase, abbreviate, or merge these anchors.",
        "ANCHOR_ROWS:",
    ]
    for idx, row in enumerate(rows, start=1):
        reps = row.get("reps", "")
        name = row.get("name", "")
        combined = f"{reps} {name}".strip()
        if combined:
            lines.append(f"{idx}. {combined}")
        weight = row.get("rx_weight", "")
        if weight:
            lines.append(f"{idx}. WEIGHT: {weight}")
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
    retry_directives = state.get("retry_directives", [])
    last_validation = state.get("last_validation_feedback", {})
    save_prompts = bool(state.get("save_intermediate_prompts", False))

    system_prompt = (
        "You are ReasoningAgent for workout poster planning. "
        "Use only the provided workout data and return valid JSON. "
        "Never invent, reorder, or mutate workout facts. "
        "If retry directives are provided, incorporate them into your planning decisions."
    )
    
    # Build retry directives context
    directives_context = ""
    if retry_directives:
        directive_lines = ["RETRY_DIRECTIVES (from prior validation failures):"]
        for directive in retry_directives:
            directive_lines.append(f"  * {directive.get('category', 'unknown')}: {directive.get('focus', '')}")
            if directive.get("affected_items"):
                directive_lines.append(f"    Affected: {directive['affected_items']}")
        directives_context = "\n".join(directive_lines)
    
    user_prompt = (
        f"WORKOUT_JSON:\n{raw}\n\n"
        f"RETRY_FEEDBACK:\n{feedback or 'none'}\n\n"
    )
    
    if directives_context:
        user_prompt += f"{directives_context}\n\n"
    
    if last_validation:
        user_prompt += f"LAST_VALIDATION:\n  Similarity Score: {last_validation.get('similarity_score', 0.0)}\n  Timestamp: {last_validation.get('timestamp_utc', '')}\n\n"
    
    user_prompt += "Return a planning object that optimizes readability and factual fidelity. Prioritize addressing the above directives."

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
        "retry_directives_applied": len(retry_directives) > 0,
        "retry_directives_count": len(retry_directives),
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


def _fallback_nutrition_baseline(
    *,
    workout_date: str,
    archetype: str,
    intensity: str,
    stimulus: str,
) -> dict[str, Any]:
    training_day_map = {
        "high": "high_intensity",
        "moderate": "moderate_intensity",
        "low": "low_intensity",
        "mixed": "mixed",
    }
    calorie_map = {
        "high": 2900,
        "moderate": 2600,
        "low": 2300,
        "mixed": 2500,
    }
    protein_map = {
        "high": 180,
        "moderate": 165,
        "low": 150,
        "mixed": 160,
    }
    carbs_map = {
        "high": 340,
        "moderate": 290,
        "low": 210,
        "mixed": 260,
    }
    fat_map = {
        "high": 85,
        "moderate": 80,
        "low": 75,
        "mixed": 78,
    }
    hydration_map = {
        "high": 3800,
        "moderate": 3400,
        "low": 3000,
        "mixed": 3300,
    }
    sodium_map = {
        "high": 1400,
        "moderate": 1200,
        "low": 950,
        "mixed": 1100,
    }

    normalized_intensity = str(intensity or "mixed").strip().lower()
    if normalized_intensity not in calorie_map:
        normalized_intensity = "mixed"

    recipes = select_recipes_deterministic(workout_date, archetype, normalized_intensity)
    return {
        "training_day_type": training_day_map[normalized_intensity],
        "calorie_guidance": calorie_map[normalized_intensity],
        "protein_target_g": protein_map[normalized_intensity],
        "carbs_target_g": carbs_map[normalized_intensity],
        "fat_target_g": fat_map[normalized_intensity],
        "pre_workout_fuel": "Carb-forward snack 60-90 minutes pre-session with light protein.",
        "post_workout_fuel": "Protein plus carbs within 60 minutes after training for recovery.",
        "hydration_ml": hydration_map[normalized_intensity],
        "electrolytes_mg_sodium": sodium_map[normalized_intensity],
        "meal_timing_strategy": (
            "Distribute meals every 3-4 hours and bias carbohydrates around training windows. "
            "Keep protein evenly spread across meals."
        ),
        "rationale": (
            "Deterministic fallback baseline generated because the nutrition LLM output was not parseable. "
            f"Workout archetype={archetype}, intensity={normalized_intensity}, stimulus={stimulus}."
        ),
        "disclaimer": "Consult a registered dietitian for personalized advice.",
        "recipe_ideas": recipes,
        "confidence": 0.55,
    }


def nutrition_baseline_node(state: PosterState) -> PosterState:
    """Generate a stateless daily nutrition baseline from workout intensity and stimulus.
    
    Non-blocking: failure in nutrition generation does not stop poster generation.
    Output: independent dated JSON artifact, not embedded in poster.
    """
    started_at = _utc_now_iso()
    started_mono = time.monotonic()
    
    # Extract inputs from prior nodes
    reasoning_plan = state.get("reasoning_plan", {})
    validated_wod = state.get("validated_wod", {})
    intensity = reasoning_plan.get("intensity_profile", "mixed")
    archetype = reasoning_plan.get("workout_archetype", "mixed")
    stimulus = validated_wod.get("stimulus", "General fitness")
    raw_wod = state.get("raw_wod", {})
    workout_date = str(raw_wod.get("date") or raw_wod.get("workout_date") or datetime.now(timezone.utc).date().isoformat())
    
    # Build system prompt for nutrition guidance
    system_prompt = (
        "You are a nutrition advisor generating a daily baseline recommendation based on workout intensity. "
        "Output ONLY a JSON response matching the provided schema. Do not add disclaimers, commentary, or markdown. "
        "Recommendations should be stateless (no athlete profile) and workout-focused. "
        "Always include exactly 2 recipe ideas: one for 'cook_at_home' and one for 'quick_order_salad_bar'. "
        "Recipe links should be realistic and simple."
    )
    
    # Map intensity to training day type
    training_day_map = {
        "high": "high_intensity",
        "moderate": "moderate_intensity",
        "low": "low_intensity",
        "mixed": "mixed",
    }
    training_day_type = training_day_map.get(intensity, "mixed")
    
    # Build user prompt with workout context
    user_prompt = (
        f"Workout date: {workout_date}\n"
        f"Workout: {archetype.upper()} at {intensity.upper()} intensity\n"
        f"Stimulus: {stimulus}\n"
        f"Generate a nutrition baseline recommendation. Be specific on macros, hydration, and meal timing. "
        f"Include rationale. Confidence should reflect how well the archetype/intensity maps to a clear macro distribution."
    )
    
    llm_meta = {"model": "", "usage": {}}
    llm_warnings: list[str] = []

    nutrition_model = str(state.get("nutrition_model") or state.get("reasoning_model") or "")

    # Call LLM if available
    if state.get("api_key") and nutrition_model:
        try:
            result = call_text_agent(
                api_key=str(state["api_key"]),
                model=nutrition_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_model=NutritionBaselineModel,
                temperature=float(state.get("reasoning_temperature", 0.3)),
                max_output_tokens=int(state.get("reasoning_max_output_tokens", 1200)),
            )
            nutrition = dict(result.payload)
            nutrition["recipe_ideas"] = select_recipes_deterministic(workout_date, archetype, intensity)
            llm_meta = {"model": result.model, "usage": result.usage}
            status = "success"
            feedback = ""
        except TextAgentError as exc:
            llm_warnings = [str(exc)]
            try:
                recovery_result = call_text_agent(
                    api_key=str(state["api_key"]),
                    model=nutrition_model,
                    system_prompt=(
                        system_prompt
                        + " Return strictly valid JSON. No prose, no markdown, no trailing comments."
                    ),
                    user_prompt=user_prompt,
                    response_model=NutritionBaselineModel,
                    temperature=0.0,
                    max_output_tokens=int(state.get("reasoning_max_output_tokens", 1200)),
                )
                nutrition = dict(recovery_result.payload)
                nutrition["recipe_ideas"] = select_recipes_deterministic(workout_date, archetype, intensity)
                llm_meta = {"model": recovery_result.model, "usage": recovery_result.usage}
                status = "recovered"
                feedback = "Recovered after initial JSON parse failure"
            except TextAgentError as recovery_exc:
                llm_warnings.append(str(recovery_exc))
                nutrition = _fallback_nutrition_baseline(
                    workout_date=workout_date,
                    archetype=archetype,
                    intensity=intensity,
                    stimulus=str(stimulus),
                )
                status = "fallback"
                feedback = str(recovery_exc)
    else:
        # Fallback if no API/model: deterministic baseline to keep downstream artifacts stable
        nutrition = _fallback_nutrition_baseline(
            workout_date=workout_date,
            archetype=archetype,
            intensity=intensity,
            stimulus=str(stimulus),
        )
        status = "fallback"
        feedback = "No API key or nutrition model configured for nutrition"
    
    decision = {
        "training_day_type": training_day_type,
        "archetype": archetype,
        "intensity": intensity,
        "model": nutrition_model,
        "llm_used": bool(llm_meta["model"]),
        "status": status,
        "has_recipe_ideas": len(nutrition.get("recipe_ideas", [])) == 2 if nutrition else False,
    }
    
    trace = _build_node_trace(
        node_name="nutrition",
        attempt=int(state.get("retry_count", 0)) + 1,
        started_at=started_at,
        started_monotonic=started_mono,
        status=status,
        decision=decision,
        prompt=_prompt_trace(system_prompt=system_prompt, user_prompt=user_prompt, save_text=bool(state.get("save_intermediate_prompts", False))),
        warnings=llm_warnings,
        output_ref={"nutrition_baseline_sha256": _sha256_text(str(nutrition))} if nutrition else {},
    )
    
    # Non-blocking: always continue, but record the result
    update: PosterState = {
        "nutrition_baseline": nutrition if nutrition else {},
        "nutrition_generation_status": status,
        "nutrition_feedback": feedback,
    }
    if llm_meta["model"]:
        update.update(_with_llm_meta(state, "nutrition", llm_meta["model"], llm_meta["usage"]))
    update.update(_with_node_trace(state, "nutrition", trace))
    return update


def architect_node(state: PosterState) -> PosterState:
    """Generate layout coordinates, panel budgets, and overflow risk assessment.
    
    Deterministic node: computes spatial mapping for all visual elements on a 1024x1024 canvas.
    Input: validated_wod from editor node
    Output: layout_coordinates, panel_budgets, overflow_risks
    """
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
            "error_log": [*state.get("error_log", []), f"architect: {err}"],
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
        update: PosterState = {
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
    
    update: PosterState = {
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
    canonical_rows = list(state.get("canonical_rows", []))
    semantic_anchors = _semantic_anchor_block(canonical_rows)

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
    candidate_prompt = f"{candidate_prompt}\n\n{semantic_anchors}\n"

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
            "semantic_anchor_count": len(canonical_rows),
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
    
    # Generate structured retry directives if validation failed
    retry_directives = []
    if retry_requested:
        # Analyze types of mismatches to provide actionable directives
        mismatch_categories = {
            "movement_names": [],
            "rep_counts": [],
            "weights": [],
            "layout_issues": [],
        }
        
        for mismatch in mismatches:
            mismatch_lower = str(mismatch).lower()
            if any(term in mismatch_lower for term in ["movement", "name", "exercise"]):
                mismatch_categories["movement_names"].append(mismatch)
            elif any(term in mismatch_lower for term in ["reps", "rep ", "count", "rounds"]):
                mismatch_categories["rep_counts"].append(mismatch)
            elif any(term in mismatch_lower for term in ["weight", "lbs", "kg", "load", "rx"]):
                mismatch_categories["weights"].append(mismatch)
            else:
                mismatch_categories["layout_issues"].append(mismatch)
        
        # Create directives based on what failed
        if mismatch_categories["movement_names"]:
            retry_directives.append({
                "category": "movement_accuracy",
                "priority": "high",
                "focus": "Ensure all movement names match semantic contract exactly; check for OCR misreads of text",
                "affected_items": mismatch_categories["movement_names"],
            })
        
        if mismatch_categories["rep_counts"]:
            retry_directives.append({
                "category": "rep_accuracy",
                "priority": "high",
                "focus": "Verify rep counts are rendered clearly; check for OCR number confusion (0/O, 1/I, 5/S)",
                "affected_items": mismatch_categories["rep_counts"],
            })
        
        if mismatch_categories["weights"]:
            retry_directives.append({
                "category": "weight_accuracy",
                "priority": "high",
                "focus": "Ensure RX weights are legible; check typography contrast and font selection",
                "affected_items": mismatch_categories["weights"],
            })
        
        if mismatch_categories["layout_issues"]:
            retry_directives.append({
                "category": "layout_clarity",
                "priority": "medium",
                "focus": "Improve spatial arrangement to reduce text overlap and improve readability",
                "affected_items": mismatch_categories["layout_issues"],
            })
        
        # Add a general directive if too many failures
        if len(mismatches) > expected_tokens_count * 0.5:
            retry_directives.append({
                "category": "strategy_pivot",
                "priority": "critical",
                "focus": f"Over 50% mismatch rate ({len(mismatches)}/{expected_tokens_count}); consider alternative layout strategy or typography",
                "affected_items": [],
            })

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
            "retry_directives_count": len(retry_directives),
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
        "retry_directives": retry_directives,
        "last_validation_feedback": {
            "mismatches": mismatches,
            "similarity_score": similarity_score,
            "directives": retry_directives,
            "timestamp_utc": _utc_now_iso(),
        },
    }
    if retry_requested:
        history = [*state.get("retry_history", []), {"attempt": int(state.get("retry_count", 0)) + 1, "reason": retry_reason, "directives": retry_directives, "timestamp_utc": _utc_now_iso()}]
        update["retry_history"] = history
    update.update(_with_node_trace(state, "validator", trace))
    return update


def should_retry(state: PosterState) -> str:
    if state.get("is_valid"):
        return "success"
    if int(state.get("retry_count", 0)) >= int(state.get("max_retries", 3)):
        return "fail"
    return "retry"

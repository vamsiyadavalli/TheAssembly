"""generate_workout_image.py — CLI to generate a workout poster image or AI image via Gemini.

Modes:
  poster  — Deterministic Pillow-based poster renderer (no API key required).
  prompt  — Export a structured Gemini-ready prompt as a .txt file.
  gemini  — Generate a real workout image using Gemini 2.0 Flash (requires GEMINI_API_KEY).

Usage (from the TheAssembly/ repo root):
    python tools/generate_workout_image.py
    python tools/generate_workout_image.py --date 2026-04-28
    python tools/generate_workout_image.py --date 2026-04-28 --mode gemini
    python tools/generate_workout_image.py --date 2026-04-28 --mode prompt
    python tools/generate_workout_image.py --date-range 2026-04-28:2026-05-01 --mode gemini
    python tools/generate_workout_image.py --date 2026-04-28 --output-dir /tmp/ai

Environment variables for gemini mode:
    GEMINI_API_KEY  (or GOOGLE_API_KEY as fallback)
    GEMINI_IMAGE_MODEL        optional model override (default: gemini-2.0-flash-preview-image-generation)
    GEMINI_IMAGE_ASPECT_RATIO optional aspect ratio override (default: 16:9)

Exit codes:
    0 — output written (or already existed, skipped)
    1 — workout not found for target date
    3 — rendering / IO error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Bootstrap: allow running from any cwd by resolving the repo root.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent           # TheAssembly/tools/
_REPO_ROOT = _SCRIPT_DIR.parent                         # TheAssembly/
_DATA_ROOT = _REPO_ROOT.parent / "TheAssemblyData"      # sibling data repo

sys.path.insert(0, str(_REPO_ROOT))

from theassembly.models import load_workouts            # noqa: E402

_DEFAULT_OUTPUT_DIR = str(_DATA_ROOT / "photos" / "ai")
_TIMEZONE = "America/New_York"


def _validate_api_key_format(api_key: str) -> None:
    """Perform a lightweight API key sanity check before network requests."""
    candidate = api_key.strip()
    if not candidate or len(candidate) < 20 or any(ch.isspace() for ch in candidate):
        raise RuntimeError(
            "[auth_failed] GEMINI_API_KEY format appears invalid. "
            "Check GEMINI_API_KEY/GOOGLE_API_KEY in env or .streamlit/secrets.toml."
        )


def _validate_prompt_preflight(prompt: str) -> None:
    """Validate prompt structure before Gemini calls to avoid low-signal generations."""
    max_chars_raw = _setting_from_env_or_secrets("GEMINI_MAX_PROMPT_CHARS", default="150000") or "150000"
    try:
        max_chars = int(max_chars_raw)
    except ValueError:
        max_chars = 150000

    if len(prompt) > max_chars:
        raise RuntimeError(
            f"[quality_failed] Prompt too long ({len(prompt)} chars). Max allowed: {max_chars}."
        )

    required_sections = (
        "Semantic Source Of Truth",
        "Header (large, bold):",
        "Workout Sections (left/middle panels with images):",
        "Design Style:",
        "WOD_ROWS:",
    )
    missing_sections = [section for section in required_sections if section not in prompt]
    if missing_sections:
        raise RuntimeError(
            "[quality_failed] Missing required prompt section(s): "
            + ", ".join(missing_sections)
        )

    wod_count_match = re.search(r"WOD_COUNT:\s*(\d+)", prompt)
    if wod_count_match is None:
        raise RuntimeError("[quality_failed] Prompt contract missing WOD_COUNT.")

    if int(wod_count_match.group(1)) <= 0:
        raise RuntimeError("[quality_failed] Prompt has no workout rows (WOD_COUNT=0).")

    wod_rows = re.findall(r"^\d+\|[^|]*\|.+$", prompt, flags=re.MULTILINE)
    if not wod_rows:
        raise RuntimeError("[quality_failed] Prompt contract has no valid WOD row entries.")


def _load_streamlit_secrets() -> dict[str, object]:
    """Load key/value secrets from .streamlit/secrets.toml when present."""
    secrets_path = _REPO_ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return {}

    try:
        return tomllib.loads(secrets_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _setting_from_env_or_secrets(
    primary_key: str,
    secondary_key: str | None = None,
    default: str | None = None,
) -> str | None:
    """Resolve settings with precedence: env -> secondary env -> secrets -> default."""
    import os

    value = os.environ.get(primary_key)
    if value:
        return value

    if secondary_key:
        value = os.environ.get(secondary_key)
        if value:
            return value

    secrets = _load_streamlit_secrets()
    candidate = secrets.get(primary_key)
    if candidate is not None and str(candidate).strip():
        return str(candidate)

    if secondary_key:
        candidate = secrets.get(secondary_key)
        if candidate is not None and str(candidate).strip():
            return str(candidate)

    return default


def _parse_args() -> argparse.Namespace:
    today = datetime.now(ZoneInfo(_TIMEZONE)).date().isoformat()
    parser = argparse.ArgumentParser(
        description="Generate a workout visualisation image (poster or AI photo)."
    )
    parser.add_argument(
        "--date",
        default=today,
        help=f"Target workout date in YYYY-MM-DD format (default: today in ET, {today})",
    )
    parser.add_argument(
        "--date-range",
        metavar="START:END",
        help="Generate for all dates from START to END inclusive (YYYY-MM-DD:YYYY-MM-DD). "
             "Overrides --date.",
    )
    parser.add_argument(
        "--mode",
        choices=["poster", "prompt", "gemini"],
        default="poster",
        help=(
            "'poster' = deterministic Pillow render (default), "
            "'prompt' = export Gemini prompt text, "
            "'gemini' = generate image via Gemini Developer API (requires GEMINI_API_KEY)"
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=_DEFAULT_OUTPUT_DIR,
        help=f"Directory to write output files into (default: {_DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--fallback",
        choices=["none", "prompt", "poster"],
        default="prompt",
        help=(
            "Fallback behavior for gemini mode quota failures: "
            "'none' = fail, 'prompt' = write prompt text, 'poster' = deterministic Pillow image"
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files instead of skipping.",
    )
    return parser.parse_args()


def _run_poster_mode(workout, output_path: Path) -> None:
    """Render a deterministic Pillow poster."""
    from theassembly.workout_poster import build_poster_spec, render_poster

    spec = build_poster_spec(workout)
    print(f"[info] Title   : {spec.title}")
    print(f"[info] Subtitle: {spec.subtitle}")
    print(f"[info] Rows    : {len(spec.rows)} movement(s) + {len(spec.finisher_rows)} finisher(s)")

    try:
        render_poster(spec, output_path)
    except Exception as exc:
        print(f"[error] Poster rendering failed: {exc}", file=sys.stderr)
        sys.exit(3)


def _run_prompt_mode(workout, output_path: Path, prompt: str | None = None) -> str:
    """Export a structured Gemini prompt to a .txt file and print to stdout."""
    from theassembly.workout_image import build_image_prompt

    prompt = prompt if prompt is not None else build_image_prompt(workout)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(prompt, encoding="utf-8")
    print(f"[info] Prompt chars: {len(prompt)}")
    print("\n" + "=" * 60)
    print(prompt)
    print("=" * 60 + "\n")
    return prompt


def _run_gemini_mode(workout, output_path: Path, prompt: str | None = None) -> tuple[str, str, str, dict[str, object]]:
    """Generate an AI workout image via Gemini Developer API and save as PNG.

    Raises:
        RuntimeError: on API failure, no image returned, or missing API key.
            Callers should catch this and decide whether to abort or continue.
    """
    from theassembly.workout_image import (
        GeminiAPIError,
        GeminiImageError,
        build_image_prompt,
        generate_gemini_image,
    )

    api_key = _setting_from_env_or_secrets("GEMINI_API_KEY", "GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY (or GOOGLE_API_KEY) is not set. "
            "Set it in shell env or .streamlit/secrets.toml before running gemini mode."
        )
    _validate_api_key_format(api_key)

    model = _setting_from_env_or_secrets(
        "GEMINI_IMAGE_MODEL",
        default="gemini-2.0-flash-preview-image-generation",
    ) or "gemini-2.0-flash-preview-image-generation"
    aspect_ratio = _setting_from_env_or_secrets(
        "GEMINI_IMAGE_ASPECT_RATIO",
        default="16:9",
    ) or "16:9"
    max_retries_raw = _setting_from_env_or_secrets("GEMINI_MAX_RETRIES", default="5") or "5"
    max_retry_delay_raw = _setting_from_env_or_secrets(
        "GEMINI_MAX_RETRY_DELAY_SECONDS",
        default="300",
    ) or "300"
    retry_jitter_raw = _setting_from_env_or_secrets("GEMINI_RETRY_JITTER_RATIO", default="0.1") or "0.1"

    try:
        max_retries = max(0, int(max_retries_raw))
    except ValueError:
        max_retries = 5

    try:
        max_retry_delay_seconds = max(1.0, float(max_retry_delay_raw))
    except ValueError:
        max_retry_delay_seconds = 300.0

    try:
        retry_jitter_ratio = max(0.0, min(float(retry_jitter_raw), 0.5))
    except ValueError:
        retry_jitter_ratio = 0.1

    langgraph_enabled_raw = _setting_from_env_or_secrets("LANGGRAPH_ENABLED", default="false") or "false"
    langgraph_enabled = langgraph_enabled_raw.strip().lower() in {"1", "true", "yes", "on"}
    validation_retries_raw = _setting_from_env_or_secrets("LANGGRAPH_VALIDATION_MAX_RETRIES", default="3") or "3"
    try:
        validation_retries = max(0, int(validation_retries_raw))
    except ValueError:
        validation_retries = 3
    langgraph_trace_enabled_raw = _setting_from_env_or_secrets("LANGGRAPH_TRACE_ENABLED", default="true") or "true"
    langgraph_trace_enabled = langgraph_trace_enabled_raw.strip().lower() in {"1", "true", "yes", "on"}
    langgraph_trace_level = _setting_from_env_or_secrets("LANGGRAPH_TRACE_LEVEL", default="standard") or "standard"
    langgraph_save_prompts_raw = _setting_from_env_or_secrets("LANGGRAPH_SAVE_INTERMEDIATE_PROMPTS", default="false") or "false"
    langgraph_save_prompts = langgraph_save_prompts_raw.strip().lower() in {"1", "true", "yes", "on"}

    prompt = prompt if prompt is not None else build_image_prompt(workout)
    _validate_prompt_preflight(prompt)
    print(f"[info] Prompt chars  : {len(prompt)}")
    print(f"[info] Model         : {model}")
    print(f"[info] Aspect ratio  : {aspect_ratio}")
    print(f"[info] Max retries   : {max_retries}")
    print(f"[info] LangGraph     : {'enabled' if langgraph_enabled else 'disabled'}")

    if langgraph_enabled:
        try:
            from theassembly.langgraph_pipeline import run_poster_pipeline

            print("[info] Running LangGraph pipeline...")
            pipeline_result = run_poster_pipeline(
                raw_wod=workout.to_dict(),
                output_path=output_path,
                api_key=api_key,
                model=model,
                aspect_ratio=aspect_ratio,
                max_retries_api=max_retries,
                max_retry_delay_seconds=max_retry_delay_seconds,
                retry_jitter_ratio=retry_jitter_ratio,
                max_validation_retries=validation_retries,
                trace_enabled=langgraph_trace_enabled,
                trace_level=langgraph_trace_level,
                save_intermediate_prompts=langgraph_save_prompts,
            )
            if not pipeline_result.get("is_valid", False):
                feedback = str(pipeline_result.get("feedback", "unknown validation error"))
                raise RuntimeError(f"[quality_failed] LangGraph validation failed: {feedback}")

            prompt = str(pipeline_result.get("final_graphic_prompt") or prompt)
            image_metrics = dict(pipeline_result.get("image_metrics") or {})
            image_metrics["langgraph_enabled"] = 1
            image_metrics["langgraph_retry_count"] = int(pipeline_result.get("retry_count", 0))
            image_metrics["langgraph_similarity_score"] = float(pipeline_result.get("similarity_score", 0.0))
            image_metrics["langgraph_validation_passed"] = 1 if pipeline_result.get("is_valid") else 0
            image_metrics["langgraph_feedback"] = str(pipeline_result.get("feedback", ""))
            image_metrics["langgraph_trace_path"] = str(pipeline_result.get("trace_path", ""))
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"[quality_failed] LangGraph pipeline failed: {exc}") from exc
    else:
        print("[info] Calling Gemini API...")
        try:
            image_metrics = generate_gemini_image(
                prompt=prompt,
                output_path=output_path,
                api_key=api_key,
                model=model,
                aspect_ratio=aspect_ratio,
                max_retries=max_retries,
                max_retry_delay_seconds=max_retry_delay_seconds,
                retry_jitter_ratio=retry_jitter_ratio,
            )
            image_metrics = image_metrics or {}
        except GeminiAPIError as exc:
            raise RuntimeError(f"[{exc.info.category}] {exc.info.message}") from exc
        except GeminiImageError as exc:
            raise RuntimeError(f"[quality_failed] {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"Gemini API call failed: {exc}") from exc

        image_metrics["langgraph_enabled"] = 0

    return prompt, model, aspect_ratio, image_metrics


def _iter_date_range(start_iso: str, end_iso: str):
    """Yield date objects from start to end inclusive."""
    current = date.fromisoformat(start_iso)
    end = date.fromisoformat(end_iso)
    while current <= end:
        yield current
        current += timedelta(days=1)


def _error_category(error_message: str) -> str:
    if error_message.startswith("[") and "]" in error_message:
        return error_message[1:error_message.find("]")]
    return "unknown"


def _run_fallback(workout, output_path: Path, fallback_mode: str, prompt: str | None = None) -> tuple[bool, str, str | None]:
    """Run configured fallback and return (success, summary)."""
    if fallback_mode == "none":
        return False, "no-fallback", None

    if fallback_mode == "prompt":
        prompt_path = output_path.with_suffix(".txt")
        used_prompt = _run_prompt_mode(workout, prompt_path, prompt=prompt)
        print(f"[fallback] Saved prompt → {prompt_path}")
        return True, "fallback-prompt", used_prompt

    if fallback_mode == "poster":
        _run_poster_mode(workout, output_path)
        print(f"[fallback] Saved poster → {output_path}")
        return True, "fallback-poster", prompt

    return False, "fallback-invalid", prompt


def _prompt_sha256(prompt: str | None) -> str | None:
    if prompt is None:
        return None
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _write_metadata(meta_path: Path, payload: dict[str, object]) -> None:
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _process_date(target_date: date, args: argparse.Namespace, all_records: list) -> tuple[int, str]:
    """Process a single date. Returns (exit_code, outcome_label)."""
    date_iso = target_date.isoformat()
    output_dir = Path(args.output_dir)
    ext = "txt" if args.mode == "prompt" else "png"  # gemini and poster both write .png
    output_path = output_dir / f"{date_iso}.{ext}"
    meta_path = output_dir / f"{date_iso}.meta.json"
    metadata: dict[str, object] = {
        "date": date_iso,
        "requested_mode": args.mode,
        "requested_fallback": args.fallback,
        "status": "unknown",
        "outcome": "unknown",
        "effective_mode": None,
        "output_path": str(output_path),
        "prompt_sha256": None,
        "model": None,
        "aspect_ratio": None,
        "prompt_length": None,
        "image_bytes": None,
        "image_width": None,
        "image_height": None,
        "validation_passed": None,
        "validation_error": None,
        "error_category": None,
        "error_message": None,
        "langgraph_enabled": None,
        "langgraph_retry_count": None,
        "langgraph_similarity_score": None,
        "langgraph_validation_passed": None,
        "langgraph_feedback": None,
        "langgraph_trace_path": None,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    if output_path.exists() and not args.overwrite:
        print(f"[skip] Already exists: {output_path}")
        metadata.update({
            "status": "skipped",
            "outcome": "skipped",
            "effective_mode": "skipped",
        })
        _write_metadata(meta_path, metadata)
        return 0, "skipped"

    workout = next((r for r in all_records if r.workout_date == target_date), None)
    if workout is None:
        print(f"[warn] No workout found for {date_iso}.", file=sys.stderr)
        metadata.update({
            "status": "not-found",
            "outcome": "not-found",
            "effective_mode": "not-found",
        })
        _write_metadata(meta_path, metadata)
        return 1, "not-found"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[info] Date    : {date_iso}")
    print(f"[info] Mode    : {args.mode}")
    print(f"[info] Output  : {output_path}")

    if args.mode == "prompt":
        prompt = _run_prompt_mode(workout, output_path)
        outcome = "prompt"
        metadata.update({
            "status": "success",
            "outcome": outcome,
            "effective_mode": "prompt",
            "prompt_length": len(prompt),
            "prompt_sha256": _prompt_sha256(prompt),
            "validation_passed": True,
        })
    elif args.mode == "gemini":
        prompt_for_run: str | None = None
        try:
            prompt_for_run, model, aspect_ratio, image_metrics = _run_gemini_mode(workout, output_path)
            outcome = "gemini"
            metadata.update({
                "status": "success",
                "outcome": outcome,
                "effective_mode": "gemini",
                "prompt_length": len(prompt_for_run),
                "prompt_sha256": _prompt_sha256(prompt_for_run),
                "model": model,
                "aspect_ratio": aspect_ratio,
                "image_bytes": image_metrics.get("image_bytes"),
                "image_width": image_metrics.get("image_width"),
                "image_height": image_metrics.get("image_height"),
                "validation_passed": True,
                "langgraph_enabled": bool(image_metrics.get("langgraph_enabled", 0)),
                "langgraph_retry_count": image_metrics.get("langgraph_retry_count"),
                "langgraph_similarity_score": image_metrics.get("langgraph_similarity_score"),
                "langgraph_validation_passed": (
                    bool(image_metrics.get("langgraph_validation_passed"))
                    if image_metrics.get("langgraph_enabled", 0)
                    else None
                ),
                "langgraph_feedback": image_metrics.get("langgraph_feedback"),
                "langgraph_trace_path": image_metrics.get("langgraph_trace_path"),
            })
        except RuntimeError as exc:
            error_text = str(exc)
            category = _error_category(error_text)
            print(f"[error] {date_iso}: {error_text}", file=sys.stderr)
            metadata.update({
                "status": "error",
                "outcome": f"failed-{category}",
                "effective_mode": "gemini",
                "validation_passed": False if category == "quality_failed" else None,
                "validation_error": error_text if category == "quality_failed" else None,
                "error_category": category,
                "error_message": error_text,
            })

            if category == "quota_exhausted":
                print(
                    "[hint] Quota exhausted. Check billing/quota at: "
                    "https://ai.google.dev/gemini-api/docs/rate-limits",
                    file=sys.stderr,
                )

            if category in {"quota_exhausted", "quality_failed"}:
                fallback_ok, fallback_outcome, fallback_prompt = _run_fallback(
                    workout,
                    output_path,
                    args.fallback,
                    prompt=prompt_for_run,
                )
                if fallback_ok:
                    print(f"[done] Saved via fallback ({args.fallback})")
                    metadata.update({
                        "status": "success",
                        "outcome": f"{fallback_outcome}-{category}",
                        "effective_mode": args.fallback,
                        "prompt_length": len(fallback_prompt) if fallback_prompt is not None else None,
                        "prompt_sha256": _prompt_sha256(fallback_prompt),
                        "validation_passed": False if category == "quality_failed" else None,
                        "validation_error": error_text if category == "quality_failed" else None,
                    })
                    _write_metadata(meta_path, metadata)
                    return 0, f"{fallback_outcome}-{category}"

            _write_metadata(meta_path, metadata)
            return 3, f"failed-{category}"
    else:
        _run_poster_mode(workout, output_path)
        outcome = "poster"
        metadata.update({
            "status": "success",
            "outcome": outcome,
            "effective_mode": "poster",
        })

    _write_metadata(meta_path, metadata)
    print(f"[done] Saved → {output_path}")
    return 0, outcome


def main() -> None:
    args = _parse_args()

    workouts_path = _DATA_ROOT / "workouts.json"
    if not workouts_path.exists():
        print(f"[error] workouts.json not found at {workouts_path}", file=sys.stderr)
        sys.exit(3)
    all_records = load_workouts(workouts_path.read_text(encoding="utf-8"))

    if args.date_range:
        # Batch mode — process every date in the range.
        try:
            start_iso, end_iso = args.date_range.split(":")
        except ValueError:
            print("[error] --date-range must be in START:END format, e.g. 2026-04-28:2026-05-01",
                  file=sys.stderr)
            sys.exit(3)
        results = [
            _process_date(d, args, all_records)
            for d in _iter_date_range(start_iso, end_iso)
        ]
        exit_codes = [code for code, _ in results]

        outcome_counts: dict[str, int] = {}
        for _, outcome in results:
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        summary_parts = [f"{k}={v}" for k, v in sorted(outcome_counts.items())]
        print(f"[summary] {', '.join(summary_parts)}")

        # Exit 1 if every date had no workout.
        # Exit 3 if any date had a generation error (but others may have succeeded).
        # Exit 0 if all were ok or skipped.
        if all(c == 1 for c in exit_codes):
            sys.exit(1)
        elif any(c == 3 for c in exit_codes):
            failed = sum(1 for c in exit_codes if c == 3)
            print(f"[warn] {failed} date(s) failed Gemini generation — check errors above.", file=sys.stderr)
            sys.exit(3)
        else:
            sys.exit(0)
    else:
        # Single date mode.
        target_date = date.fromisoformat(args.date)
        code, _ = _process_date(target_date, args, all_records)
        sys.exit(code)


if __name__ == "__main__":
    main()

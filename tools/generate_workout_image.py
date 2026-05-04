"""generate_workout_image.py — CLI to generate a workout poster image or AI image via Gemini.

Modes:
  poster  — Deterministic Pillow-based poster renderer (no API key required).
  prompt  — Export a structured Gemini-ready prompt as a .txt file.
  gemini  — Generate a real workout image using Gemini 2.5 Flash Image (requires GEMINI_API_KEY).

Usage (from the TheAssembly/ repo root):
    python tools/generate_workout_image.py
    python tools/generate_workout_image.py --date 2026-04-28
    python tools/generate_workout_image.py --date 2026-04-28 --mode gemini
    python tools/generate_workout_image.py --date 2026-04-28 --mode prompt
    python tools/generate_workout_image.py --date-range 2026-04-28:2026-05-01 --mode gemini
    python tools/generate_workout_image.py --date 2026-04-28 --output-dir /tmp/ai

Environment variables for gemini mode:
    GEMINI_API_KEY  (or GOOGLE_API_KEY as fallback)
    GEMINI_IMAGE_MODEL        optional model override (default: gemini-2.5-flash-image)
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


def _run_gemini_mode(workout, output_path: Path, prompt: str | None = None) -> tuple[str, str, str]:
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

    model = _setting_from_env_or_secrets(
        "GEMINI_IMAGE_MODEL",
        default="gemini-2.5-flash-image",
    ) or "gemini-2.5-flash-image"
    aspect_ratio = _setting_from_env_or_secrets(
        "GEMINI_IMAGE_ASPECT_RATIO",
        default="16:9",
    ) or "16:9"

    prompt = prompt if prompt is not None else build_image_prompt(workout)
    print(f"[info] Prompt chars  : {len(prompt)}")
    print(f"[info] Model         : {model}")
    print(f"[info] Aspect ratio  : {aspect_ratio}")
    print("[info] Calling Gemini API...")

    try:
        generate_gemini_image(
            prompt=prompt,
            output_path=output_path,
            api_key=api_key,
            model=model,
            aspect_ratio=aspect_ratio,
        )
    except GeminiAPIError as exc:
        raise RuntimeError(f"[{exc.info.category}] {exc.info.message}") from exc
    except GeminiImageError as exc:
        raise RuntimeError(f"Gemini returned no image: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Gemini API call failed: {exc}") from exc

    return prompt, model, aspect_ratio


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
        "error_category": None,
        "error_message": None,
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
            "prompt_sha256": _prompt_sha256(prompt),
        })
    elif args.mode == "gemini":
        prompt_for_run: str | None = None
        try:
            prompt_for_run, model, aspect_ratio = _run_gemini_mode(workout, output_path)
            outcome = "gemini"
            metadata.update({
                "status": "success",
                "outcome": outcome,
                "effective_mode": "gemini",
                "prompt_sha256": _prompt_sha256(prompt_for_run),
                "model": model,
                "aspect_ratio": aspect_ratio,
            })
        except RuntimeError as exc:
            error_text = str(exc)
            category = _error_category(error_text)
            print(f"[error] {date_iso}: {error_text}", file=sys.stderr)
            metadata.update({
                "status": "error",
                "outcome": f"failed-{category}",
                "effective_mode": "gemini",
                "error_category": category,
                "error_message": error_text,
            })

            if category == "quota_exhausted":
                print(
                    "[hint] Quota exhausted. Check billing/quota at: "
                    "https://ai.google.dev/gemini-api/docs/rate-limits",
                    file=sys.stderr,
                )
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
                        "outcome": fallback_outcome,
                        "effective_mode": args.fallback,
                        "prompt_sha256": _prompt_sha256(fallback_prompt),
                    })
                    _write_metadata(meta_path, metadata)
                    return 0, fallback_outcome

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

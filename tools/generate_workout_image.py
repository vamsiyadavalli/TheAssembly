"""generate_workout_image.py — CLI to generate a workout poster image.

Deterministic Pillow-based poster renderer only (no API key required).

Usage (from the TheAssembly/ repo root):
    python tools/generate_workout_image.py
    python tools/generate_workout_image.py --date 2026-04-28
    python tools/generate_workout_image.py --date 2026-04-28 --output-dir /tmp/ai

Exit codes:
    0 — image written (or already existed, skipped)
    1 — workout not found for target date
    3 — rendering / IO error
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
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
        "--mode",
        choices=["poster"],
        default="poster",
        help="'poster' = deterministic Pillow render (default)",
    )
    parser.add_argument(
        "--output-dir",
        default=_DEFAULT_OUTPUT_DIR,
        help=f"Directory to write the PNG into (default: {_DEFAULT_OUTPUT_DIR})",
    )
    return parser.parse_args()


def _load_workout_for_date(target_date: date):
    workouts_path = _DATA_ROOT / "workouts.json"
    if not workouts_path.exists():
        print(f"[error] workouts.json not found at {workouts_path}", file=sys.stderr)
        sys.exit(3)

    records = load_workouts(workouts_path.read_text(encoding="utf-8"))
    for record in records:
        if record.workout_date == target_date:
            return record
    return None


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


def main() -> None:
    args = _parse_args()

    target_date = date.fromisoformat(args.date)
    output_dir = Path(args.output_dir)
    output_path = output_dir / f"{args.date}.png"

    if output_path.exists():
        print(f"[skip] Image already exists: {output_path}")
        sys.exit(0)

    workout = _load_workout_for_date(target_date)
    if workout is None:
        print(f"[error] No workout found for date {args.date}.", file=sys.stderr)
        sys.exit(1)

    print(f"[info] Date    : {args.date}")
    print(f"[info] Mode    : {args.mode}")
    print(f"[info] Output  : {output_path}")

    _run_poster_mode(workout, output_path)

    print(f"[done] Saved → {output_path}")


if __name__ == "__main__":
    main()

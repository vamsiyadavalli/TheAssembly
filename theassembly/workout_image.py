"""workout_image.py — Build a rich visual prompt from a WorkoutRecord for AI image generation.

Used by the CLI tool (tools/generate_workout_image.py) and the GitHub Action.
Pure function — no I/O, no external dependencies.

Prompt structure (modelled on the high-fidelity CrossFit banner reference):
  1. Style intro paragraph
  2. Header  — motivational, derived from workout type / finisher presence
  3. Sub-header — workout_content uppercased
  4. Numbered movement panels for main WOD movements
  5. Finisher panel — only when section='Finisher' movements exist
  6. Footer — Stimulus + Coach Tips
  7. Design style directives

Gemini image generation:
  generate_gemini_image() calls the Gemini Developer API using the google-genai SDK.
  Requires GEMINI_API_KEY (or GOOGLE_API_KEY) in the environment.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from theassembly.models import WorkoutRecord

# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------

_STYLE_INTRO = (
    "Create a high-contrast fitness workout banner/poster with a dark gym background "
    "and a gritty, modern CrossFit-style aesthetic. Use bold white and electric blue "
    "typography, with a structured layout and clear sections. Include realistic athletic "
    "models demonstrating each movement step-by-step with arrows showing progression."
)

_STYLE_DIRECTIVES = "\n".join([
    "Design Style:",
    "* Dark/black textured background",
    "* Blue brush stroke accents",
    "* Strong contrast lighting on athletes",
    "* Clean grid layout with boxes/panels",
    "* Arrows between movement steps",
    "* Professional gym poster look (Nike/CrossFit branding style)",
    "* Keep movement numbers fully inside each panel with safe left padding",
    "* Preserve clear line spacing so numbers/text do not touch borders",
    "* 4K, ultra-detailed, sharp, cinematic lighting",
])

_SEPARATOR = "\n\n---\n\n"

# ---------------------------------------------------------------------------
# Motivational header derivation
# ---------------------------------------------------------------------------

_FINISHER_HEADER = "THERE'S A FINISHER AT THE END. PACE YOURSELF, THEN LET IT RIP."

# Ordered — first keyword match wins.
_CONTENT_HEADERS: tuple[tuple[str, str], ...] = (
    ("AMRAP",           "KEEP MOVING. EVERY REP COUNTS. HOW FAR CAN YOU GO?"),
    ("EMOM",            "WORK THE CLOCK. REST THE CLOCK. OWN EVERY MINUTE."),
    ("E2MOM",           "WORK THE CLOCK. REST THE CLOCK. OWN EVERY MINUTE."),
    ("ROUNDS FOR TIME", "EVERY ROUND FASTER THAN THE LAST. CHASE THE CLOCK."),
    ("CHIPPER",         "CHIP AWAY. IT ENDS WHEN YOU END IT. KEEP CHOPPING."),
    ("STRENGTH",        "BUILD THE BASE. LIFT WITH INTENT. EARN EVERY REP."),
    ("TEAM",            "TOGETHER IS FASTER. COMMUNICATE. MOVE AS ONE."),
)

_DEFAULT_HEADER = "BRING YOUR BEST. LEAVE IT ALL ON THE FLOOR. LET'S WORK."


def _derive_header(workout_content: str, has_finisher: bool) -> str:
    """Return a short motivational header line for the banner."""
    if has_finisher:
        return _FINISHER_HEADER
    content_upper = workout_content.upper()
    for keyword, header in _CONTENT_HEADERS:
        if keyword in content_upper:
            return header
    return _DEFAULT_HEADER


# ---------------------------------------------------------------------------
# Movement section formatter
# ---------------------------------------------------------------------------

def _format_movement_block(movements: list, numbered: bool = True) -> str:
    """Render a list of movements as a numbered or bulleted block for the prompt."""
    lines: list[str] = []
    for i, m in enumerate(movements, start=1):
        reps_part = f"{m.reps} " if m.reps else ""
        prefix = f"{i}. " if numbered else "* "
        lines.append(f"{prefix}{reps_part}{m.name}")
        # Suppress notes that are just a repeated round count (shown via group header).
        display_notes = m.notes
        if m.round_group > 0 and display_notes:
            display_notes = re.sub(
                r"^(then\s+)?\d+\s+rounds?\b[^,]*",
                "",
                display_notes,
                flags=re.IGNORECASE,
            ).strip(" ,;—–-")
        if display_notes:
            lines.append(f'   * "{display_notes}"')
        if m.rx_weight and m.scaled_weight:
            lines.append(f"   * Rx: {m.rx_weight} / Scaled: {m.scaled_weight}")
        elif m.rx_weight:
            lines.append(f"   * Weight: {m.rx_weight}")
        elif m.scaled_weight:
            lines.append(f"   * Scaled: {m.scaled_weight}")
    return "\n".join(lines)


def _normalize_inline_text(text: str) -> str:
    """Collapse whitespace/newlines for single-line contract/footer fields."""
    return " ".join(text.split())


def _validate_poster_input(workout: "WorkoutRecord", wod_movements: list, finisher_movements: list) -> None:
    """Fail fast if movement mapping would silently drop rows."""
    ignored = [m for m in workout.movements if m not in wod_movements and m not in finisher_movements]
    if ignored:
        bad_sections = sorted({m.section.strip() for m in ignored if m.section.strip()})
        raise ValueError(
            "Unsupported movement sections for poster prompt: "
            + ", ".join(bad_sections)
        )


def _build_semantic_contract_block(wod_movements: list, finisher_movements: list) -> str:
    """Emit an explicit source-of-truth block the model must follow exactly."""
    lines: list[str] = [
        "Semantic Source Of Truth (must be followed exactly):",
        "- Do NOT add, remove, merge, or reorder movement rows.",
        "- Do NOT change reps, distances, durations, or movement names.",
        "- Keep numbering sequential and only for listed WOD rows.",
        f"WOD_COUNT: {len(wod_movements)}",
        "WOD_ROWS:",
    ]

    for idx, m in enumerate(wod_movements, start=1):
        reps_part = _normalize_inline_text(m.reps) if m.reps else ""
        name_part = _normalize_inline_text(m.name)
        lines.append(f"{idx}|{reps_part}|{name_part}")

    if finisher_movements:
        part_nums = sorted({m.finisher_part for m in finisher_movements if m.finisher_part > 0})
        if len(part_nums) >= 2:
            lines.append(f"FINISHER_PARTS: {len(part_nums)}")
            for part_num in part_nums:
                part_mvmts = [m for m in finisher_movements if m.finisher_part == part_num]
                first = part_mvmts[0]
                part_title = first.finisher_part_title or first.finisher_part_type or f"Part {part_num}"
                lines.append(f"FINISHER_PART_{part_num}_TITLE: {_normalize_inline_text(part_title)}")
                lines.append(f"FINISHER_PART_{part_num}_COUNT: {len(part_mvmts)}")
                for idx, m in enumerate(part_mvmts, start=1):
                    reps_part = _normalize_inline_text(m.reps) if m.reps else ""
                    name_part = _normalize_inline_text(m.name)
                    lines.append(f"FINISHER_PART_{part_num}_ROW_{idx}: {reps_part}|{name_part}")
        else:
            lines.append(f"FINISHER_COUNT: {len(finisher_movements)}")
            for idx, m in enumerate(finisher_movements, start=1):
                reps_part = _normalize_inline_text(m.reps) if m.reps else ""
                name_part = _normalize_inline_text(m.name)
                lines.append(f"FINISHER_ROW_{idx}: {reps_part}|{name_part}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_image_prompt(workout: "WorkoutRecord") -> str:
    """Return a structured, high-fidelity visual prompt for FLUX / Hugging Face.

    The prompt is section-structured (no length truncation) and deterministic —
    running it twice on the same WorkoutRecord produces identical output.

    Finisher panel is included only when one or more movements carry
    ``section='Finisher'``.
    """
    wod_movements = [m for m in workout.movements if not m.section.strip()]
    finisher_movements = [
        m for m in workout.movements if m.section.strip().lower() == "finisher"
    ]
    _validate_poster_input(workout, wod_movements, finisher_movements)
    has_finisher = bool(finisher_movements)

    header = _derive_header(workout.workout_content, has_finisher)
    subheader = workout.workout_content.upper()

    sections: list[str] = []

    # 1 — Style intro
    sections.append(_STYLE_INTRO)

    # 1b — Semantic source-of-truth contract (must remain deterministic)
    sections.append(_build_semantic_contract_block(wod_movements, finisher_movements))

    # 2 & 3 — Header / Sub-header
    sections.append(
        f'Header (large, bold):\n"{header}"\n\n'
        f'Sub-header (highlighted bar):\n"{subheader}"'
    )

    # 4 — Main WOD movement panels
    if wod_movements:
        body = "Workout Sections (left/middle panels with images):\n\n"
        # Group by round_group when explicit metadata exists; fall back to flat list.
        rg_map: dict[int, list] = {}
        ungrouped_wod: list = []
        for m in wod_movements:
            if m.round_group > 0:
                if m.round_group not in rg_map:
                    rg_map[m.round_group] = []
                rg_map[m.round_group].append(m)
            else:
                ungrouped_wod.append(m)

        if rg_map:
            prompt_lines: list[str] = []
            if ungrouped_wod:
                prompt_lines.append(_format_movement_block(ungrouped_wod, numbered=True))
            for rg_num in sorted(rg_map):
                group = rg_map[rg_num]
                label = group[0].round_group_label or f"Group {rg_num}"
                note = group[0].round_group_note
                header = f'"{label.upper()}"'
                if note:
                    header += f' — {note}'
                prompt_lines.append(header)
                prompt_lines.append(_format_movement_block(group, numbered=True))
            body += "\n\n".join(prompt_lines)
        else:
            body += _format_movement_block(wod_movements, numbered=True)
        sections.append(body)

    # 5 — Finisher panel (conditional)
    if has_finisher:
        finisher_lines = ['Finisher Panel (right side, bold & highlighted):\nTitle: "FINISHER"']

        # Group by finisher_part when explicit metadata exists; fall back to flat list.
        part_nums = sorted({m.finisher_part for m in finisher_movements if m.finisher_part > 0})
        if len(part_nums) >= 2:
            for part_num in part_nums:
                part_mvmts = [m for m in finisher_movements if m.finisher_part == part_num]
                first = part_mvmts[0]
                part_title = first.finisher_part_title or first.finisher_part_type or f"Part {part_num}"
                finisher_lines.append(f'"PART {part_num}: {part_title.upper()}"')
                for m in part_mvmts:
                    reps_part = f"{m.reps} \u2013 " if m.reps else ""
                    finisher_lines.append(f'  "{reps_part}{m.name}"')
        else:
            for m in finisher_movements:
                reps_part = f"{m.reps} \u2013 " if m.reps else ""
                finisher_lines.append(f'"{reps_part}{m.name}"')
                if m.notes:
                    finisher_lines.append(f'"{m.notes.upper()}"')

        sections.append("\n".join(finisher_lines))

    # 6 — Footer
    footer_parts: list[str] = []
    if workout.stimulus:
        footer_parts.append(f'* Stimulus: "{_normalize_inline_text(workout.stimulus)}"')
    if workout.technical_cues:
        cues_text = _normalize_inline_text(" ".join(workout.technical_cues))
        footer_parts.append(f'* Coach Tips: "{cues_text}"')
    if footer_parts:
        sections.append("Footer Sections:\n\n" + "\n".join(footer_parts))

    # 7 — Design style directives
    sections.append(_STYLE_DIRECTIVES)

    return _SEPARATOR.join(sections)


# ---------------------------------------------------------------------------
# Gemini image generation
# ---------------------------------------------------------------------------

class GeminiImageError(Exception):
    """Raised when Gemini fails to return an image."""


@dataclass(frozen=True)
class GeminiErrorInfo:
    category: str
    retry_after_seconds: float | None
    message: str


class GeminiAPIError(Exception):
    """Raised when Gemini API calls fail with classified metadata."""

    def __init__(self, info: GeminiErrorInfo) -> None:
        self.info = info
        super().__init__(info.message)


def _extract_retry_after_seconds(raw_message: str) -> float | None:
    """Extract retry delay seconds from Gemini error text when present."""
    retry_delay_match = re.search(r"retryDelay'?:\s*'?(\d+(?:\.\d+)?)s", raw_message)
    if retry_delay_match:
        return float(retry_delay_match.group(1))

    retry_in_match = re.search(r"retry in\s+(\d+(?:\.\d+)?)s", raw_message, re.IGNORECASE)
    if retry_in_match:
        return float(retry_in_match.group(1))

    return None


def _classify_gemini_error(exc: Exception) -> GeminiErrorInfo:
    """Classify Gemini API failures for retry/fallback behavior."""
    message = str(exc)
    lowered = message.lower()
    retry_after = _extract_retry_after_seconds(message)

    if "resource_exhausted" in lowered or "quota exceeded" in lowered:
        return GeminiErrorInfo("quota_exhausted", retry_after, message)
    if "rate limit" in lowered or ("429" in lowered and retry_after is not None):
        return GeminiErrorInfo("rate_limited", retry_after, message)
    if "401" in lowered or "permission_denied" in lowered or "api key" in lowered:
        return GeminiErrorInfo("auth_failed", None, message)
    if "not_found" in lowered and "model" in lowered:
        return GeminiErrorInfo("model_not_found", None, message)

    return GeminiErrorInfo("unknown", retry_after, message)


def generate_gemini_image(
    prompt: str,
    output_path: "Path",
    api_key: str,
    model: str = "gemini-2.5-flash-image",
    aspect_ratio: str = "16:9",
    max_retries: int = 2,
) -> None:
    """Call Gemini Developer API to generate a workout image and save it as PNG.

    Args:
        prompt: The structured text prompt from build_image_prompt().
        output_path: Destination path for the generated PNG file.
        api_key: Gemini Developer API key (GEMINI_API_KEY or GOOGLE_API_KEY).
        model: Gemini model ID that supports native image generation.
        aspect_ratio: Desired aspect ratio, e.g. "16:9" or "1:1".

    Raises:
        GeminiImageError: If the API call succeeds but returns no image part.
        Exception: Any network or authentication error from the google-genai SDK.
    """
    from pathlib import Path as _Path

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "google-genai is not installed. Run: pip install google-genai"
        ) from exc

    client = genai.Client(api_key=api_key)

    response = None
    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                    image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
                ),
            )
            break
        except Exception as exc:
            info = _classify_gemini_error(exc)

            # Quota exhaustion on free tier is usually non-recoverable in the same run.
            if info.category == "quota_exhausted":
                raise GeminiAPIError(info) from exc

            is_retryable = info.category == "rate_limited"
            has_attempts_left = attempt < max_retries
            if not (is_retryable and has_attempts_left):
                raise GeminiAPIError(info) from exc

            sleep_seconds = info.retry_after_seconds if info.retry_after_seconds is not None else min(2 ** attempt, 8)
            time.sleep(min(sleep_seconds, 15))

    if response is None:
        raise GeminiAPIError(
            GeminiErrorInfo("unknown", None, "Gemini API call failed without a response")
        )

    image_data: bytes | None = None
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            image_data = part.inline_data.data
            break

    if image_data is None:
        raise GeminiImageError(
            f"Gemini returned no image part for prompt starting: {prompt[:120]!r}"
        )

    dest = _Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(image_data)

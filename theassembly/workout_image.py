"""workout_image.py — Build a rich visual prompt from a WorkoutRecord for AI image generation.

Used by the CLI tool (tools/generate_workout_image.py) and the GitHub Action.
Pure function — no I/O, no external dependencies.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from theassembly.models import WorkoutRecord

_STYLE_SUFFIX = (
    "cinematic sports photography, dramatic gym lighting, "
    "multiple athletes in motion, high energy, dark athletic facility, action shot"
)

_MAX_PROMPT_CHARS = 400


def build_image_prompt(workout: "WorkoutRecord") -> str:
    """Return a rich visual prompt string suitable for FLUX.1-schnell or SDXL.

    Combines the workout title, stimulus, and primary WOD movements (skipping
    named finisher sections).  A fixed style suffix is appended and the result
    is truncated to ``_MAX_PROMPT_CHARS`` characters to stay within model limits.
    """
    parts: list[str] = []

    if workout.workout_content:
        parts.append(workout.workout_content.strip())

    if workout.stimulus:
        parts.append(workout.stimulus.strip())

    # Primary WOD movements only — exclude named sections like "Finisher".
    wod_movements = [m for m in workout.movements if not m.section.strip()]
    if wod_movements:
        movement_phrases = []
        for m in wod_movements:
            phrase = m.name.strip()
            if m.reps:
                phrase = f"{m.reps} {phrase}"
            movement_phrases.append(phrase)
        parts.append(", ".join(movement_phrases))

    body = ". ".join(parts)
    prompt = f"{body}. {_STYLE_SUFFIX}"

    if len(prompt) > _MAX_PROMPT_CHARS:
        # Trim the body, keeping the style suffix intact.
        max_body = _MAX_PROMPT_CHARS - len(_STYLE_SUFFIX) - 2  # 2 for ". "
        prompt = f"{body[:max_body].rstrip('. ')}. {_STYLE_SUFFIX}"

    return prompt

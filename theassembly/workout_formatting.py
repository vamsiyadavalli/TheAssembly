"""workout_formatting.py — UI-friendly HTML rendering for workout records.

When a WorkoutRecord includes structured ``movements``, renders a flex-row list
grouped by section (WOD first, then named sections like "Finisher" in a visually
distinct block).  Falls back to the raw ``workout_content`` text for legacy
records that have no structured movements.

This module is intentionally UI-agnostic (plain HTML strings) so that the same
output can be embedded in Streamlit, Jinja templates, or any other surface.
"""
from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from theassembly.models import Movement, WorkoutRecord


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def format_workout_html(record: "WorkoutRecord") -> str:
    """Return UI-ready HTML for a workout record.

    Uses structured movements when present; falls back gracefully to
    the legacy ``workout_content`` plain-text block.
    """
    if record.movements:
        return _render_structured(record.workout_content, record.movements)
    return _render_legacy(record.workout_content)


def format_workout_summary(record: "WorkoutRecord") -> str:
    """Return a plain-text one-liner suitable for admin list / search index."""
    if record.movements:
        names = ", ".join(m.name for m in record.movements)
        return f"{record.workout_content} | {names}"
    # Take first non-empty line of legacy content as the summary.
    for line in record.workout_content.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return record.workout_content


# ---------------------------------------------------------------------------
# Internal renderers
# ---------------------------------------------------------------------------

def _render_legacy(content: str) -> str:
    return f'<div class="workout-legacy">{escape(content)}</div>'


def _render_structured(header: str, movements: tuple["Movement", ...]) -> str:
    # Group movements preserving insertion order; "" = primary WOD block.
    sections: dict[str, list["Movement"]] = {}
    for m in movements:
        key = m.section.strip()
        if key not in sections:
            sections[key] = []
        sections[key].append(m)

    parts: list[str] = []

    if header.strip():
        parts.append(f'<div class="workout-structured-header">{escape(header)}</div>')

    for section_name, mvmts in sections.items():
        rows = "".join(_movement_row(m) for m in mvmts)
        if section_name:
            parts.append(
                f'<div class="movement-finisher-block">'
                f'<div class="movement-section-label">{escape(section_name)}</div>'
                f'<div class="movement-list">{rows}</div>'
                f'</div>'
            )
        else:
            parts.append(f'<div class="movement-list">{rows}</div>')

    return "".join(parts)


def _movement_row(m: "Movement") -> str:
    reps_html = f'<span class="mvmt-reps">{escape(m.reps)}</span>' if m.reps else ""
    name_html = f'<span class="mvmt-name">{escape(m.name)}</span>'
    badges = ""
    if m.rx_weight:
        badges += f'<span class="rx-badge">{escape(m.rx_weight)}</span>'
    if m.scaled_weight:
        badges += f'<span class="scaled-badge">{escape(m.scaled_weight)}</span>'
    badges_html = f'<span class="movement-badges">{badges}</span>' if badges else ""
    notes_html = f'<div class="mvmt-notes">{escape(m.notes)}</div>' if m.notes else ""

    return (
        f'<div class="movement-row">'
        f'<div class="movement-row-main">'
        f'<span class="movement-row-left">{reps_html}{name_html}</span>'
        f'{badges_html}'
        f'</div>'
        f'{notes_html}'
        f'</div>'
    )

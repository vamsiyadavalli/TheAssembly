"""workout_formatting.py — UI-friendly HTML rendering for workout records.

When a WorkoutRecord includes structured ``movements``, renders a table with
explicit Rx and Scaled weight columns.  Falls back to the raw ``workout_content``
text for legacy records that have no structured movements.

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
    has_rx = any(m.rx_weight for m in movements)
    has_scaled = any(m.scaled_weight for m in movements)
    has_notes = any(m.notes for m in movements)

    rows_html = "".join(
        _movement_row(m, has_rx=has_rx, has_scaled=has_scaled, has_notes=has_notes)
        for m in movements
    )

    # Build thead columns dynamically so the table is compact when weights are absent.
    th_reps = '<th class="mvmt-reps">Reps</th>'
    th_name = '<th class="mvmt-name">Movement</th>'
    th_rx = '<th class="mvmt-rx">Rx</th>' if has_rx else ""
    th_scaled = '<th class="mvmt-scaled">Scaled</th>' if has_scaled else ""
    th_notes = '<th class="mvmt-notes">Notes</th>' if has_notes else ""

    header_html = (
        f'<div class="workout-structured-header">{escape(header)}</div>'
        if header.strip()
        else ""
    )

    return (
        f'{header_html}'
        f'<table class="movement-table">'
        f'<thead><tr>{th_reps}{th_name}{th_rx}{th_scaled}{th_notes}</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table>'
    )


def _movement_row(
    m: "Movement",
    *,
    has_rx: bool,
    has_scaled: bool,
    has_notes: bool,
) -> str:
    td_reps = f'<td class="mvmt-reps">{escape(m.reps)}</td>'
    td_name = f'<td class="mvmt-name">{escape(m.name)}</td>'

    td_rx = ""
    if has_rx:
        badge = (
            f'<span class="rx-badge">{escape(m.rx_weight)}</span>'
            if m.rx_weight
            else '<span class="weight-none">—</span>'
        )
        td_rx = f'<td class="mvmt-rx">{badge}</td>'

    td_scaled = ""
    if has_scaled:
        badge = (
            f'<span class="scaled-badge">{escape(m.scaled_weight)}</span>'
            if m.scaled_weight
            else '<span class="weight-none">—</span>'
        )
        td_scaled = f'<td class="mvmt-scaled">{badge}</td>'

    td_notes = ""
    if has_notes:
        td_notes = f'<td class="mvmt-notes">{escape(m.notes)}</td>'

    return f"<tr>{td_reps}{td_name}{td_rx}{td_scaled}{td_notes}</tr>"

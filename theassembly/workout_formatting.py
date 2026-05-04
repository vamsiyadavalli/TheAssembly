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
        if section_name:
            parts.append(_render_section_block(section_name, mvmts))
        else:
            parts.append(_render_wod_block(mvmts))

    return "".join(parts)


def _render_section_block(section_name: str, mvmts: list["Movement"]) -> str:
    """Render a named section (e.g. Finisher), grouping by finisher_part when present."""
    # Collect distinct part numbers > 0 in insertion order.
    seen_parts: dict[int, list["Movement"]] = {}
    ungrouped: list["Movement"] = []
    for m in mvmts:
        if m.finisher_part > 0:
            if m.finisher_part not in seen_parts:
                seen_parts[m.finisher_part] = []
            seen_parts[m.finisher_part].append(m)
        else:
            ungrouped.append(m)

    # Multi-part: at least two distinct part numbers → show part headers.
    if len(seen_parts) >= 2:
        inner_html = _render_finisher_parts(seen_parts, ungrouped)
    else:
        # Single explicit part or no explicit parts → flat list (no extra headers).
        all_mvmts = list(mvmts)
        inner_html = f'<div class="movement-list">{"".join(_movement_row(m) for m in all_mvmts)}</div>'

    return (
        f'<div class="movement-finisher-block">'
        f'<div class="movement-section-label">{escape(section_name)}</div>'
        f'{inner_html}'
        f'</div>'
    )


def _render_finisher_parts(
    part_groups: dict[int, list["Movement"]],
    ungrouped: list["Movement"],
) -> str:
    """Render grouped finisher parts with part-level subheaders."""
    html_pieces: list[str] = []

    # Render any ungrouped movements first (rare, backward-compat)
    if ungrouped:
        rows = "".join(_movement_row(m) for m in ungrouped)
        html_pieces.append(f'<div class="movement-list finisher-part-list">{rows}</div>')

    for idx, part_num in enumerate(sorted(part_groups)):
        part_mvmts = part_groups[part_num]
        first = part_mvmts[0]
        part_label = f"Part {part_num}"
        # Use title if supplied, fall back to type, fall back to empty.
        part_detail = first.finisher_part_title or first.finisher_part_type
        is_first = idx == 0 and not ungrouped
        html_pieces.append(_finisher_part_header(part_label, part_detail, is_first=is_first))
        rows = "".join(_movement_row(m) for m in part_mvmts)
        html_pieces.append(f'<div class="movement-list finisher-part-list">{rows}</div>')

    return "".join(html_pieces)


def _finisher_part_header(label: str, detail: str, *, is_first: bool = False) -> str:
    margin = "" if is_first else ' style="margin-top:0.9rem"'
    detail_html = (
        f'<span class="finisher-part-detail">{escape(detail)}</span>' if detail else ""
    )
    return (
        f'<div class="finisher-part-header"{margin}>'
        f'<span class="finisher-part-label">{escape(label)}</span>'
        f'{detail_html}'
        f'</div>'
    )


def _render_wod_block(mvmts: list["Movement"]) -> str:
    """Render the primary WOD movement list, grouping by round_group when present."""
    # Collect movements by round_group (> 0 = grouped, 0 = ungrouped).
    groups: dict[int, list["Movement"]] = {}
    ungrouped: list["Movement"] = []
    for m in mvmts:
        if m.round_group > 0:
            if m.round_group not in groups:
                groups[m.round_group] = []
            groups[m.round_group].append(m)
        else:
            ungrouped.append(m)

    if not groups:
        # No explicit grouping — legacy flat list.
        rows = "".join(_movement_row(m) for m in mvmts)
        return f'<div class="movement-list">{rows}</div>'

    html_pieces: list[str] = []

    # Ungrouped movements first (e.g. buy-in reps before the round block).
    if ungrouped:
        rows = "".join(_movement_row(m) for m in ungrouped)
        html_pieces.append(f'<div class="movement-list">{rows}</div>')

    for group_num in sorted(groups):
        group_mvmts = groups[group_num]
        first = group_mvmts[0]
        label = first.round_group_label or f"Group {group_num}"
        note = first.round_group_note
        html_pieces.append(_wod_round_group_header(label, note))
        rows = "".join(_movement_row(m, in_round_group=True) for m in group_mvmts)
        html_pieces.append(f'<div class="movement-list wod-round-group-list">{rows}</div>')

    return "".join(html_pieces)


def _wod_round_group_header(label: str, note: str = "") -> str:
    note_html = (
        f'<span class="wod-round-group-note">{escape(note)}</span>' if note else ""
    )
    return (
        f'<div class="wod-round-group-header">'
        f'<span class="wod-round-group-label">{escape(label)}</span>'
        f'{note_html}'
        f'</div>'
    )


def _movement_row(m: "Movement", *, in_round_group: bool = False) -> str:
    reps_html = f'<span class="mvmt-reps">{escape(m.reps)}</span>' if m.reps else ""
    name_html = f'<span class="mvmt-name">{escape(m.name)}</span>'
    badges = ""
    if m.rx_weight:
        badges += f'<span class="rx-badge">{escape(m.rx_weight)}</span>'
    if m.scaled_weight:
        badges += f'<span class="scaled-badge">{escape(m.scaled_weight)}</span>'
    badges_html = f'<span class="movement-badges">{badges}</span>' if badges else ""

    # When a movement is explicitly assigned to a finisher part, suppress any
    # legacy "Part N —" prefix from notes so the same text isn't shown twice.
    display_notes = m.notes
    if m.finisher_part > 0 and display_notes:
        import re as _re
        display_notes = _re.sub(r"^Part\s+\d+\s*[—\-–]\s*", "", display_notes).strip()

    # When rendered inside a round group, the group header already carries the
    # rounds label — suppress it from per-movement notes to avoid repetition.
    if in_round_group and display_notes:
        import re as _re
        display_notes = _re.sub(
            r"^(then\s+)?\d+\s+rounds?\b[^,]*",
            "",
            display_notes,
            flags=_re.IGNORECASE,
        ).strip(" ,;—–-")

    notes_html = f'<div class="mvmt-notes">{escape(display_notes)}</div>' if display_notes else ""

    return (
        f'<div class="movement-row">'
        f'<div class="movement-row-main">'
        f'<span class="movement-row-left">{reps_html}{name_html}</span>'
        f'{badges_html}'
        f'</div>'
        f'{notes_html}'
        f'</div>'
    )

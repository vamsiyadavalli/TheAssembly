"""Tests for workout_formatting.py — structured HTML rendering including multi-part finishers."""
from __future__ import annotations

import unittest
from theassembly.models import Movement, WorkoutRecord
from theassembly.workout_formatting import format_workout_html


def _record(movements: list[dict], content: str = "5 Rounds for Time") -> "WorkoutRecord":
    return WorkoutRecord.from_dict({
        "date": "2026-05-04",
        "release_time": "20:00",
        "content": content,
        "stimulus": "Test",
        "technical_cues": ["Stay consistent."],
        "movements": movements,
    })


class LegacyFinisherRenderingTests(unittest.TestCase):
    """Records without finisher_part fields should render identically to before."""

    def test_single_finisher_renders_flat(self) -> None:
        rec = _record([
            {"name": "Wall Balls", "reps": "12"},
            {"name": "Group Mile Run", "reps": "1 mile", "section": "Finisher"},
        ])
        html = format_workout_html(rec)
        self.assertIn("movement-finisher-block", html)
        self.assertIn("Group Mile Run", html)
        # No part headers should be emitted
        self.assertNotIn("finisher-part-header", html)

    def test_two_legacy_finisher_movements_flat(self) -> None:
        rec = _record([
            {"name": "Burpees", "reps": "10"},
            {"name": "Hollow Rocks", "reps": "45s", "section": "Finisher"},
            {"name": "Flutter Kicks", "reps": "45s", "section": "Finisher"},
        ])
        html = format_workout_html(rec)
        self.assertIn("Hollow Rocks", html)
        self.assertIn("Flutter Kicks", html)
        self.assertNotIn("finisher-part-header", html)


class MultiPartFinisherRenderingTests(unittest.TestCase):
    """Records with explicit finisher_part fields should render grouped part headers."""

    def _two_part_movements(self) -> list[dict]:
        return [
            {"name": "Push-Ups", "reps": "30"},
            {"name": "Flutter Kicks", "reps": "20s", "section": "Finisher",
             "finisher_part": 1, "finisher_part_type": "Tabata", "finisher_part_title": "4:00 Tabata"},
            {"name": "Plate Getups", "reps": "20s", "section": "Finisher",
             "finisher_part": 1, "finisher_part_type": "Tabata", "finisher_part_title": "4:00 Tabata"},
            {"name": "Pull Ups", "reps": "6-8", "section": "Finisher",
             "finisher_part": 2, "finisher_part_type": "EMOM", "finisher_part_title": "12:00 EMOM"},
        ]

    def test_two_parts_emit_part_headers(self) -> None:
        html = format_workout_html(_record(self._two_part_movements()))
        self.assertIn("finisher-part-header", html)
        self.assertIn("Part 1", html)
        self.assertIn("Part 2", html)

    def test_part_titles_shown_in_detail_span(self) -> None:
        html = format_workout_html(_record(self._two_part_movements()))
        self.assertIn("finisher-part-detail", html)
        self.assertIn("4:00 Tabata", html)
        self.assertIn("12:00 EMOM", html)

    def test_all_movements_present(self) -> None:
        html = format_workout_html(_record(self._two_part_movements()))
        for name in ("Flutter Kicks", "Plate Getups", "Pull Ups"):
            self.assertIn(name, html)

    def test_part_notes_prefix_suppressed(self) -> None:
        """Legacy 'Part N —' prefix in notes should not appear when explicit part fields present."""
        movements = [
            {"name": "Hollow Rocks", "reps": "20s", "section": "Finisher",
             "notes": "Part 1 — 4:00 Tabata",
             "finisher_part": 1, "finisher_part_type": "Tabata", "finisher_part_title": "4:00 Tabata"},
            {"name": "Air Squats", "reps": "10", "section": "Finisher",
             "notes": "Part 2 — 12:00 EMOM",
             "finisher_part": 2, "finisher_part_type": "EMOM", "finisher_part_title": "12:00 EMOM"},
        ]
        html = format_workout_html(_record(movements))
        # "Part 1 —" prefix must not appear; the part detail header already shows it
        self.assertNotIn("Part 1 \u2014", html)
        self.assertNotIn("Part 2 \u2014", html)

    def test_single_explicit_part_no_part_header(self) -> None:
        """Single finisher_part (only part=1) should still render flat with no part header."""
        rec = _record([
            {"name": "Burpees", "reps": "5"},
            {"name": "Hollow Rocks", "reps": "45s", "section": "Finisher",
             "finisher_part": 1, "finisher_part_type": "Tabata"},
        ])
        html = format_workout_html(rec)
        self.assertNotIn("finisher-part-header", html)

    def test_wod_movements_not_in_finisher_block(self) -> None:
        html = format_workout_html(_record(self._two_part_movements()))
        # The WOD movement should appear outside the finisher block
        self.assertIn("Push-Ups", html)


if __name__ == "__main__":
    unittest.main()

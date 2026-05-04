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


class WodRoundGroupRenderingTests(unittest.TestCase):
    """Movements with round_group metadata should render under a shared group header."""

    def _may4_movements(self) -> list[dict]:
        """May 4 pattern: buy-in + 10-round pair."""
        return [
            {"name": "Push-Ups", "reps": "60", "notes": "Each set buy-in"},
            {"name": "Alternating Dumbbell Power Snatch", "reps": "6",
             "round_group": 1, "round_group_label": "10 Rounds"},
            {"name": "Air Squat", "reps": "12",
             "round_group": 1, "round_group_label": "10 Rounds"},
        ]

    def test_group_header_appears_once(self) -> None:
        html = format_workout_html(_record(self._may4_movements()))
        self.assertEqual(html.count("10 Rounds"), 1)

    def test_both_movements_present(self) -> None:
        html = format_workout_html(_record(self._may4_movements()))
        self.assertIn("Alternating Dumbbell Power Snatch", html)
        self.assertIn("Air Squat", html)

    def test_group_header_css_class(self) -> None:
        html = format_workout_html(_record(self._may4_movements()))
        self.assertIn("wod-round-group-header", html)
        self.assertIn("wod-round-group-label", html)

    def test_ungrouped_buy_in_still_renders(self) -> None:
        html = format_workout_html(_record(self._may4_movements()))
        self.assertIn("Push-Ups", html)

    def test_group_note_renders(self) -> None:
        movements = [
            {"name": "Alternating Farmer Step Up", "reps": "30",
             "round_group": 1, "round_group_label": "3 Rounds",
             "round_group_note": "Rest 2:00 between rounds"},
            {"name": "Run", "reps": "400m",
             "round_group": 1, "round_group_label": "3 Rounds"},
        ]
        html = format_workout_html(_record(movements))
        self.assertIn("Rest 2:00 between rounds", html)
        self.assertIn("wod-round-group-note", html)

    def test_legacy_movements_render_flat(self) -> None:
        """Records with no round_group fields should render exactly as before."""
        rec = _record([
            {"name": "Pull-ups", "reps": "10", "notes": "5 rounds"},
            {"name": "Box Jumps", "reps": "15", "notes": "5 rounds"},
        ])
        html = format_workout_html(rec)
        self.assertNotIn("wod-round-group-header", html)
        self.assertIn("Pull-ups", html)
        self.assertIn("Box Jumps", html)

    def test_multiple_groups_render_all_headers(self) -> None:
        movements = [
            {"name": "Squat Clean", "reps": "5",
             "round_group": 1, "round_group_label": "5 Rounds"},
            {"name": "Ring Dips", "reps": "10",
             "round_group": 2, "round_group_label": "3 Rounds"},
        ]
        html = format_workout_html(_record(movements))
        self.assertIn("5 Rounds", html)
        self.assertIn("3 Rounds", html)
        self.assertEqual(html.count("wod-round-group-header"), 2)

    def test_finisher_grouping_unaffected(self) -> None:
        """Adding round_group to WOD movements must not disturb finisher part grouping."""
        movements = [
            {"name": "Snatch", "reps": "6", "round_group": 1, "round_group_label": "10 Rounds"},
            {"name": "Air Squat", "reps": "12", "round_group": 1, "round_group_label": "10 Rounds"},
            {"name": "Flutter Kicks", "reps": "20s", "section": "Finisher",
             "finisher_part": 1, "finisher_part_title": "4:00 Tabata"},
            {"name": "Pull Ups", "reps": "6", "section": "Finisher",
             "finisher_part": 2, "finisher_part_title": "12:00 EMOM"},
        ]
        html = format_workout_html(_record(movements))
        self.assertIn("wod-round-group-header", html)
        self.assertIn("finisher-part-header", html)


if __name__ == "__main__":
    unittest.main()

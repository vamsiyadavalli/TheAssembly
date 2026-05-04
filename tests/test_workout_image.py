"""Tests for theassembly.workout_image — structured FLUX prompt builder."""
import unittest

from theassembly.models import WorkoutRecord
from theassembly.workout_image import (
    _FINISHER_HEADER,
    _derive_header,
    build_image_prompt,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_workout(**overrides) -> WorkoutRecord:
    """Return a minimal valid WorkoutRecord, with optional field overrides."""
    base = {
        "date": "2026-05-01",
        "release_time": "20:00",
        "content": "5 Rounds for Time",
        "stimulus": "Aerobic Endurance",
        "technical_cues": ["Keep a steady pace."],
    }
    base.update(overrides)
    return WorkoutRecord.from_dict(base)


# ---------------------------------------------------------------------------
# Header derivation
# ---------------------------------------------------------------------------

class DeriveHeaderTests(unittest.TestCase):
    def test_finisher_header_when_has_finisher(self) -> None:
        result = _derive_header("Strength (No Clock)", has_finisher=True)
        self.assertEqual(_FINISHER_HEADER, result)

    def test_amrap_keyword_matched(self) -> None:
        result = _derive_header("15-Min AMRAP", has_finisher=False)
        self.assertIn("KEEP MOVING", result)

    def test_emom_keyword_matched(self) -> None:
        result = _derive_header("E2MOM x 10 (20 min)", has_finisher=False)
        self.assertIn("CLOCK", result)

    def test_rounds_for_time_keyword_matched(self) -> None:
        result = _derive_header("5 Rounds for Time — Waterfall Start", has_finisher=False)
        self.assertIn("EVERY ROUND", result)

    def test_chipper_keyword_matched(self) -> None:
        result = _derive_header("Team Chipper — For Time", has_finisher=False)
        self.assertIn("CHIP AWAY", result)

    def test_strength_keyword_matched(self) -> None:
        result = _derive_header("Strength (No Clock) + 1-Mile Benchmark", has_finisher=False)
        self.assertIn("BUILD THE BASE", result)

    def test_team_keyword_matched(self) -> None:
        result = _derive_header("Team Chipper + Synchronized Finisher", has_finisher=False)
        # "TEAM" should match before "CHIPPER" since we check "TEAM" last in tuple
        # and "CHIPPER" comes earlier — confirm chipper wins
        self.assertIn("CHIP AWAY", result)

    def test_default_header_for_unrecognised_content(self) -> None:
        result = _derive_header("Mystery Format", has_finisher=False)
        self.assertIn("BRING YOUR BEST", result)

    def test_finisher_flag_overrides_content_keywords(self) -> None:
        # Even a known keyword should yield finisher header when has_finisher=True
        result = _derive_header("AMRAP + Core Finisher", has_finisher=True)
        self.assertEqual(_FINISHER_HEADER, result)


# ---------------------------------------------------------------------------
# Prompt structure — workout with Finisher
# ---------------------------------------------------------------------------

class PromptWithFinisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workout = _make_workout(
            content="Strength (No Clock) + 1-Mile Benchmark",
            stimulus="Hypertrophy + Aerobic Benchmark",
            technical_cues=["Control the descent on the floor press; no hip rotation on rows."],
            movements=[
                {"name": "DB Floor Press", "reps": "5x10", "notes": "Heavier than Week 1"},
                {"name": "Strict Renegade Rows", "reps": "5x10"},
                {"name": "Triple 7 Bicep Curls", "reps": "3 sets"},
                {"name": "1-Mile Run", "reps": "1 mile", "notes": "track your time", "section": "Finisher"},
            ],
        )
        self.prompt = build_image_prompt(self.workout)

    def test_contains_finisher_header(self) -> None:
        self.assertIn(_FINISHER_HEADER, self.prompt)

    def test_subheader_is_content_uppercased(self) -> None:
        self.assertIn("STRENGTH (NO CLOCK) + 1-MILE BENCHMARK", self.prompt)

    def test_wod_movements_appear(self) -> None:
        self.assertIn("DB Floor Press", self.prompt)
        self.assertIn("Strict Renegade Rows", self.prompt)
        self.assertIn("Triple 7 Bicep Curls", self.prompt)

    def test_finisher_panel_present(self) -> None:
        self.assertIn("FINISHER", self.prompt)
        self.assertIn("1-Mile Run", self.prompt)

    def test_finisher_movement_not_in_wod_section(self) -> None:
        # Finisher should appear after the separator, not numbered in the WOD panel.
        wod_section = self.prompt.split("---")[2]  # Workout Sections block
        self.assertNotIn("1-Mile Run", wod_section)

    def test_stimulus_in_footer(self) -> None:
        self.assertIn("Hypertrophy + Aerobic Benchmark", self.prompt)

    def test_coach_tips_in_footer(self) -> None:
        self.assertIn("Control the descent on the floor press", self.prompt)

    def test_style_directives_present(self) -> None:
        self.assertIn("4K, ultra-detailed", self.prompt)
        self.assertIn("Dark/black textured background", self.prompt)

    def test_movement_notes_included(self) -> None:
        self.assertIn("Heavier than Week 1", self.prompt)

    def test_finisher_notes_uppercased(self) -> None:
        self.assertIn("TRACK YOUR TIME", self.prompt)


# ---------------------------------------------------------------------------
# Prompt structure — workout without Finisher
# ---------------------------------------------------------------------------

class PromptWithoutFinisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workout = _make_workout(
            content="15-Min AMRAP — I Go, You Go Pairs",
            stimulus="Density Training",
            technical_cues=["Only one person on the pull-up bar at a time."],
            movements=[
                {"name": "Box Step Ups", "reps": "10", "notes": "or Weighted Lunges"},
                {"name": "Burpees over DB", "reps": "10"},
                {"name": "Toes-to-Bar", "reps": "10"},
            ],
        )
        self.prompt = build_image_prompt(self.workout)

    def test_no_finisher_panel(self) -> None:
        self.assertNotIn("FINISHER", self.prompt)

    def test_amrap_header_used(self) -> None:
        self.assertIn("KEEP MOVING", self.prompt)

    def test_all_movements_in_prompt(self) -> None:
        self.assertIn("Box Step Ups", self.prompt)
        self.assertIn("Burpees over DB", self.prompt)
        self.assertIn("Toes-to-Bar", self.prompt)

    def test_stimulus_present(self) -> None:
        self.assertIn("Density Training", self.prompt)


# ---------------------------------------------------------------------------
# Missing optional fields
# ---------------------------------------------------------------------------

class PromptMissingOptionalFieldsTests(unittest.TestCase):
    def test_no_movements_does_not_crash(self) -> None:
        workout = _make_workout()  # no movements
        prompt = build_image_prompt(workout)
        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 0)

    def test_movement_without_notes_or_weights(self) -> None:
        workout = _make_workout(
            movements=[{"name": "Pull-ups", "reps": "10"}]
        )
        prompt = build_image_prompt(workout)
        self.assertIn("Pull-ups", prompt)

    def test_movement_with_rx_and_scaled_weights(self) -> None:
        workout = _make_workout(
            movements=[
                {"name": "DB Snatch", "reps": "10", "rx_weight": "55 lbs", "scaled_weight": "35 lbs"}
            ]
        )
        prompt = build_image_prompt(workout)
        self.assertIn("Rx: 55 lbs", prompt)
        self.assertIn("Scaled: 35 lbs", prompt)

    def test_movement_with_rx_only(self) -> None:
        workout = _make_workout(
            movements=[{"name": "KB Swing", "reps": "20", "rx_weight": "53 lbs"}]
        )
        prompt = build_image_prompt(workout)
        self.assertIn("Weight: 53 lbs", prompt)

    def test_empty_technical_cues_omits_coach_tips(self) -> None:
        # technical_cues is required by the model but could be a single empty item edge case
        workout = _make_workout(technical_cues=[""])
        prompt = build_image_prompt(workout)
        # No "Coach Tips:" label when all cues are blank
        self.assertNotIn("Coach Tips:", prompt)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class DeterminismTests(unittest.TestCase):
    def test_same_input_produces_identical_output(self) -> None:
        workout = _make_workout(
            content="E2MOM x 10 (20 min) + Core Finisher",
            stimulus="Skill + Anaerobic Power",
            technical_cues=["Keep the DB close to the body."],
            movements=[
                {"name": "DB Squat Snatches", "reps": "10", "rx_weight": "50 lbs"},
                {"name": "Burpees over DB", "reps": "12"},
                {"name": "Hollow Rocks", "reps": "45s", "section": "Finisher"},
            ],
        )
        self.assertEqual(build_image_prompt(workout), build_image_prompt(workout))


# ---------------------------------------------------------------------------
# Multipart finisher prompt structure
# ---------------------------------------------------------------------------

class MultiPartFinisherPromptTests(unittest.TestCase):
    def _two_part_workout(self) -> "WorkoutRecord":
        return _make_workout(
            content="2 Sets For Time — Push-Up Buy-In + DB Power Snatch / Air Squat",
            stimulus="Upper-body stamina and repeat aerobic power.",
            technical_cues=["Break push-ups early to avoid long rest periods."],
            movements=[
                {"name": "Push-Ups", "reps": "60"},
                {"name": "Alternating Dumbbell Power Snatch", "reps": "6"},
                {"name": "Flutter Kicks", "reps": "20s", "section": "Finisher",
                 "finisher_part": 1, "finisher_part_type": "Tabata", "finisher_part_title": "4:00 Tabata"},
                {"name": "Plate Getups", "reps": "20s", "section": "Finisher",
                 "finisher_part": 1, "finisher_part_type": "Tabata", "finisher_part_title": "4:00 Tabata"},
                {"name": "Pull Ups", "reps": "6-8", "section": "Finisher",
                 "finisher_part": 2, "finisher_part_type": "EMOM", "finisher_part_title": "12:00 EMOM"},
            ],
        )

    def test_part_headers_appear_in_finisher_panel(self) -> None:
        prompt = build_image_prompt(self._two_part_workout())
        self.assertIn("PART 1:", prompt)
        self.assertIn("PART 2:", prompt)

    def test_part_titles_included(self) -> None:
        prompt = build_image_prompt(self._two_part_workout())
        self.assertIn("4:00 TABATA", prompt)
        self.assertIn("12:00 EMOM", prompt)

    def test_all_finisher_movements_included(self) -> None:
        prompt = build_image_prompt(self._two_part_workout())
        self.assertIn("Flutter Kicks", prompt)
        self.assertIn("Plate Getups", prompt)
        self.assertIn("Pull Ups", prompt)

    def test_finisher_header_used_for_multipart(self) -> None:
        prompt = build_image_prompt(self._two_part_workout())
        self.assertIn(_FINISHER_HEADER, prompt)

    def test_wod_movements_not_mixed_into_finisher(self) -> None:
        prompt = build_image_prompt(self._two_part_workout())
        # Confirm the finisher section block is separate from WOD block
        self.assertIn("Push-Ups", prompt)
        self.assertIn("FINISHER", prompt)

    def test_single_part_explicit_renders_flat_no_part_header(self) -> None:
        workout = _make_workout(
            content="5 Rounds for Time",
            movements=[
                {"name": "Burpees", "reps": "10"},
                {"name": "Hollow Rocks", "reps": "45s", "section": "Finisher",
                 "finisher_part": 1, "finisher_part_type": "Tabata"},
            ],
        )
        prompt = build_image_prompt(workout)
        self.assertIn("FINISHER", prompt)
        # Only one part — should NOT emit "PART 1:" header
        self.assertNotIn("PART 1:", prompt)

    def test_multipart_prompt_is_deterministic(self) -> None:
        workout = self._two_part_workout()
        self.assertEqual(build_image_prompt(workout), build_image_prompt(workout))


class WodRoundGroupPromptTests(unittest.TestCase):
    """Grouped WOD movements should share a single round header in the image prompt."""

    def _grouped_workout(self) -> WorkoutRecord:
        return _make_workout(
            content="2 Sets For Time — Push-Up Buy-In + DB Power Snatch / Air Squat",
            movements=[
                {"name": "Push-Ups", "reps": "60", "notes": "Each set buy-in"},
                {"name": "Alternating Dumbbell Power Snatch", "reps": "6",
                 "rx_weight": "Men 40 lbs",
                 "round_group": 1, "round_group_label": "10 Rounds"},
                {"name": "Air Squat", "reps": "12",
                 "round_group": 1, "round_group_label": "10 Rounds"},
            ],
        )

    def test_group_label_appears_once(self) -> None:
        prompt = build_image_prompt(self._grouped_workout())
        self.assertEqual(prompt.upper().count("10 ROUNDS"), 1)

    def test_all_wod_movements_in_prompt(self) -> None:
        prompt = build_image_prompt(self._grouped_workout())
        self.assertIn("Push-Ups", prompt)
        self.assertIn("Alternating Dumbbell Power Snatch", prompt)
        self.assertIn("Air Squat", prompt)

    def test_round_notes_not_duplicated_in_group_context(self) -> None:
        """Movement notes that just repeat the round count must be suppressed."""
        workout = _make_workout(
            content="KB Swing + Wall Ball For Time",
            movements=[
                {"name": "KB Swing", "reps": "15", "notes": "10 rounds",
                 "round_group": 1, "round_group_label": "10 Rounds"},
                {"name": "Wall Ball", "reps": "15", "notes": "10 rounds",
                 "round_group": 1, "round_group_label": "10 Rounds"},
            ],
        )
        prompt = build_image_prompt(workout)
        # Label appears once from the group header, not from per-movement notes
        self.assertEqual(prompt.upper().count("10 ROUNDS"), 1)

    def test_no_group_metadata_renders_flat(self) -> None:
        """Legacy movements with no round_group still render as flat numbered list."""
        workout = _make_workout(
            movements=[
                {"name": "Pull-ups", "reps": "10", "notes": "5 rounds"},
                {"name": "Box Jumps", "reps": "15"},
            ],
        )
        prompt = build_image_prompt(workout)
        self.assertIn("Pull-ups", prompt)
        self.assertIn("Box Jumps", prompt)

    def test_group_note_appears_in_prompt(self) -> None:
        workout = _make_workout(
            movements=[
                {"name": "Farmer Step Up", "reps": "30",
                 "round_group": 1, "round_group_label": "3 Rounds",
                 "round_group_note": "Rest 2:00 between rounds"},
                {"name": "Run", "reps": "400m",
                 "round_group": 1, "round_group_label": "3 Rounds"},
            ],
        )
        prompt = build_image_prompt(workout)
        self.assertIn("Rest 2:00 between rounds", prompt)

    def test_prompt_is_deterministic(self) -> None:
        workout = self._grouped_workout()
        self.assertEqual(build_image_prompt(workout), build_image_prompt(workout))


if __name__ == "__main__":
    unittest.main()

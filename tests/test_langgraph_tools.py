from __future__ import annotations

import unittest

from theassembly.langgraph_pipeline.tools import (
    ToolExecutionError,
    generate_coordinate_map,
    get_brand_assets,
    validate_workout_schema,
    verify_image_accuracy,
)


class ValidateWorkoutSchemaTests(unittest.TestCase):
    def test_validates_required_movement_fields(self) -> None:
        payload = {
            "date": "2026-05-11",
            "release_time": "16:00",
            "content": "9 Rounds",
            "stimulus": "High-Intensity Grit",
            "technical_cues": ["Stay smooth"],
            "movements": [
                {"name": "V-Ups", "reps": "9", "round_group_label": "9 Rounds"},
                {"name": "Box Jumps", "reps": "9", "round_group_label": "9 Rounds"},
            ],
        }
        validated = validate_workout_schema(payload)
        self.assertEqual(validated["movements"][0]["name"], "V-Ups")

    def test_round_group_label_must_be_contiguous(self) -> None:
        payload = {
            "date": "2026-05-11",
            "release_time": "16:00",
            "content": "Test",
            "stimulus": "Test",
            "technical_cues": ["Cue"],
            "movements": [
                {"name": "A", "reps": "1", "round_group_label": "Group 1"},
                {"name": "B", "reps": "1"},
                {"name": "C", "reps": "1", "round_group_label": "Group 1"},
            ],
        }
        with self.assertRaises(ToolExecutionError):
            validate_workout_schema(payload)


class GenerateCoordinateMapTests(unittest.TestCase):
    def test_reserves_sidebar_when_finisher_exists(self) -> None:
        validated = {
            "date": "2026-05-11",
            "release_time": "16:00",
            "content": "Test",
            "stimulus": "Test",
            "technical_cues": ["Cue"],
            "movements": [
                {"name": "A", "reps": "1"},
                {"name": "B", "reps": "1", "section": "Finisher"},
            ],
        }
        coords = generate_coordinate_map(validated)
        self.assertTrue(coords["has_finisher"])
        self.assertIsNotNone(coords["zones"]["sidebar"])
        self.assertLess(coords["zones"]["header"]["width"], 1024)


class BrandAssetsTests(unittest.TestCase):
    def test_returns_deterministic_palette(self) -> None:
        assets = get_brand_assets("High-Intensity Grit")
        self.assertEqual(assets["palette"]["accent"], "#007BFF")
        self.assertIn("lighting", assets)


class VerifyImageAccuracyTests(unittest.TestCase):
    def test_similarity_score_full_match(self) -> None:
        expected = [
            {"name": "V-Ups", "reps": "9", "rx_weight": ""},
            {"name": "Push Jerk", "reps": "9", "rx_weight": "Men 40 lbs / Women 25 lbs"},
        ]

        def fake_extractor(_: str) -> str:
            return "9 V-Ups\n9 Push Jerk\nMen 40 lbs / Women 25 lbs"

        result = verify_image_accuracy("unused.jpg", expected, text_extractor=fake_extractor)
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["similarity_score"], 1.0)

    def test_similarity_score_partial_match(self) -> None:
        expected = [
            {"name": "V-Ups", "reps": "9", "rx_weight": ""},
            {"name": "Push Jerk", "reps": "9", "rx_weight": "Men 40 lbs / Women 25 lbs"},
        ]

        def fake_extractor(_: str) -> str:
            return "9 V-Ups\n9 Push Jerk"

        result = verify_image_accuracy("unused.jpg", expected, text_extractor=fake_extractor)
        self.assertFalse(result["is_valid"])
        self.assertLess(result["similarity_score"], 1.0)


if __name__ == "__main__":
    unittest.main()

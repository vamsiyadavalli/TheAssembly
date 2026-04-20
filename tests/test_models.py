import unittest

from theassembly.github_repo import build_text_update_payload, build_update_payload
from theassembly.models import WorkoutRecord, load_current_state, load_workouts


class WorkoutModelTests(unittest.TestCase):
    def test_load_workouts_accepts_canonical_content_key(self) -> None:
        raw_text = """
        [
          {
            "date": "2026-04-20",
            "release_time": "05:30",
            "content": "Run 1 mile",
            "stimulus": "Benchmark pace",
            "technical_cues": ["Relax shoulders"]
          }
        ]
        """

        records = load_workouts(raw_text)

        self.assertEqual(1, len(records))
        self.assertEqual("Run 1 mile", records[0].workout_content)

    def test_load_workouts_accepts_title_case_keys(self) -> None:
        raw_text = """
        [
          {
            "Date": "2026-04-20",
            "Release Time": "05:30",
            "Workout Content": "Run 1 mile",
            "Stimulus": "Benchmark pace",
            "Technical Cues": ["Relax shoulders"]
          }
        ]
        """

        records = load_workouts(raw_text)

        self.assertEqual(1, len(records))
        self.assertEqual("2026-04-20", records[0].date)
        self.assertEqual(("Relax shoulders",), records[0].technical_cues)

    def test_serialize_uses_canonical_content_key(self) -> None:
        record = WorkoutRecord.from_dict(
            {
                "date": "2026-04-20",
                "release_time": "05:30",
                "workout_content": "Run 1 mile",
                "stimulus": "Benchmark pace",
                "technical_cues": ["Relax shoulders"],
            }
        )

        payload = record.to_dict()

        self.assertIn("content", payload)
        self.assertNotIn("workout_content", payload)
        self.assertEqual("Run 1 mile", payload["content"])

    def test_load_current_state_accepts_open(self) -> None:
        state = load_current_state('{"status": "open"}')

        self.assertTrue(state.is_open)

    def test_current_state_rejects_unknown_status(self) -> None:
        with self.assertRaises(ValueError):
            load_current_state('{"status": "paused"}')

    def test_duplicate_dates_are_rejected(self) -> None:
        raw_text = """
        [
          {
            "date": "2026-04-20",
            "release_time": "05:30",
            "workout_content": "A",
            "stimulus": "B",
            "technical_cues": ["C"]
          },
          {
            "date": "2026-04-20",
            "release_time": "06:30",
            "workout_content": "D",
            "stimulus": "E",
            "technical_cues": ["F"]
          }
        ]
        """

        with self.assertRaises(ValueError):
            load_workouts(raw_text)

    def test_update_payload_base64_encodes_json(self) -> None:
        record = WorkoutRecord.from_dict(
            {
                "date": "2026-04-20",
                "release_time": "05:30",
                "workout_content": "Run 1 mile",
                "stimulus": "Benchmark pace",
                "technical_cues": ["Relax shoulders"],
            }
        )

        payload = build_update_payload([record], message="Save workout", sha="abc123", branch="main")

        self.assertEqual("Save workout", payload["message"])
        self.assertEqual("abc123", payload["sha"])
        self.assertIn("content", payload)

    def test_text_payload_base64_encodes_state(self) -> None:
        payload = build_text_update_payload('{\n  "status": "open"\n}\n', message="Open slate", sha=None, branch="main")

        self.assertEqual("Open slate", payload["message"])
        self.assertEqual("main", payload["branch"])
        self.assertIn("content", payload)


if __name__ == "__main__":
    unittest.main()

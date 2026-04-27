import unittest

from theassembly.github_repo import build_text_update_payload, build_update_payload
from theassembly.models import Movement, WorkoutRecord, load_current_state, load_workouts


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


class MovementModelTests(unittest.TestCase):
    def test_movement_from_dict_parses_all_fields(self) -> None:
        m = Movement.from_dict(
            {"name": "DB Snatches", "reps": "15", "rx_weight": "55 lbs", "scaled_weight": "35 lbs", "notes": "Alt. arms"}
        )

        self.assertEqual("DB Snatches", m.name)
        self.assertEqual("15", m.reps)
        self.assertEqual("55 lbs", m.rx_weight)
        self.assertEqual("35 lbs", m.scaled_weight)
        self.assertEqual("Alt. arms", m.notes)

    def test_movement_from_dict_requires_name(self) -> None:
        with self.assertRaises(ValueError):
            Movement.from_dict({"reps": "10", "rx_weight": "45 lbs"})

    def test_movement_to_dict_omits_empty_fields(self) -> None:
        m = Movement.from_dict({"name": "200m Run", "reps": "1"})
        d = m.to_dict()

        self.assertEqual({"name": "200m Run", "reps": "1"}, d)
        self.assertNotIn("rx_weight", d)
        self.assertNotIn("scaled_weight", d)
        self.assertNotIn("notes", d)

    def test_workout_record_accepts_structured_movements(self) -> None:
        raw_text = """
        [
          {
            "date": "2026-05-10",
            "release_time": "05:30",
            "content": "5 Rounds for Time",
            "stimulus": "Strength endurance",
            "technical_cues": ["Breathe at the top"],
            "movements": [
              {"name": "DB Snatches", "reps": "15", "rx_weight": "55 lbs", "scaled_weight": "35 lbs"},
              {"name": "200m Run", "reps": "1"}
            ]
          }
        ]
        """

        records = load_workouts(raw_text)

        self.assertEqual(1, len(records))
        self.assertEqual(2, len(records[0].movements))
        self.assertEqual("DB Snatches", records[0].movements[0].name)
        self.assertEqual("55 lbs", records[0].movements[0].rx_weight)
        self.assertEqual("35 lbs", records[0].movements[0].scaled_weight)
        self.assertEqual("200m Run", records[0].movements[1].name)
        self.assertEqual("", records[0].movements[1].rx_weight)

    def test_workout_record_movements_round_trip(self) -> None:
        record = WorkoutRecord.from_dict(
            {
                "date": "2026-05-10",
                "release_time": "05:30",
                "content": "5 Rounds for Time",
                "stimulus": "Strength endurance",
                "technical_cues": ["Breathe at the top"],
                "movements": [
                    {"name": "DB Snatches", "reps": "15", "rx_weight": "55 lbs", "scaled_weight": "35 lbs"},
                    {"name": "200m Run", "reps": "1"},
                ],
            }
        )

        serialized = record.to_dict()

        self.assertIn("movements", serialized)
        self.assertEqual(2, len(serialized["movements"]))
        self.assertEqual("DB Snatches", serialized["movements"][0]["name"])
        self.assertEqual("55 lbs", serialized["movements"][0]["rx_weight"])
        # Empty fields are not serialized.
        self.assertNotIn("rx_weight", serialized["movements"][1])

    def test_workout_record_without_movements_omits_movements_key(self) -> None:
        record = WorkoutRecord.from_dict(
            {
                "date": "2026-05-11",
                "release_time": "05:30",
                "content": "Legacy content text",
                "stimulus": "Aerobic base",
                "technical_cues": ["Stay steady"],
            }
        )

        serialized = record.to_dict()

        self.assertNotIn("movements", serialized)
        self.assertEqual((), record.movements)

    def test_mixed_legacy_and_structured_records_load_together(self) -> None:
        raw_text = """
        [
          {
            "date": "2026-05-10",
            "release_time": "05:30",
            "content": "Structured day",
            "stimulus": "Power",
            "technical_cues": ["Hips first"],
            "movements": [{"name": "Deadlift", "reps": "5", "rx_weight": "225 lbs", "scaled_weight": "135 lbs"}]
          },
          {
            "date": "2026-05-11",
            "release_time": "05:30",
            "content": "Legacy free-text day",
            "stimulus": "Endurance",
            "technical_cues": ["Breathe"]
          }
        ]
        """

        records = load_workouts(raw_text)

        self.assertEqual(2, len(records))
        structured = next(r for r in records if r.date == "2026-05-10")
        legacy = next(r for r in records if r.date == "2026-05-11")
        self.assertEqual(1, len(structured.movements))
        self.assertEqual(0, len(legacy.movements))

    def test_malformed_movement_entry_raises(self) -> None:
        raw_text = """
        [
          {
            "date": "2026-05-10",
            "release_time": "05:30",
            "content": "Bad movements",
            "stimulus": "Test",
            "technical_cues": ["Cue"],
            "movements": [{"reps": "10"}]
          }
        ]
        """

        with self.assertRaises(ValueError):
            load_workouts(raw_text)

    def test_movement_section_field_parsed(self) -> None:
        m = Movement.from_dict({"name": "Hollow Rocks", "reps": "45s", "section": "Finisher"})

        self.assertEqual("Finisher", m.section)

    def test_movement_to_dict_omits_empty_section(self) -> None:
        m = Movement.from_dict({"name": "Wall Balls", "reps": "12"})
        d = m.to_dict()

        self.assertNotIn("section", d)
        self.assertEqual("", m.section)

    def test_movement_section_round_trip(self) -> None:
        original = {"name": "Flutter Kicks", "reps": "45s", "notes": "3 rounds", "section": "Finisher"}
        m = Movement.from_dict(original)
        d = m.to_dict()

        self.assertEqual("Finisher", d["section"])
        self.assertEqual("3 rounds", d["notes"])


class CaptionModelTests(unittest.TestCase):
    def _base(self) -> dict:
        return {
            "date": "2026-05-10",
            "release_time": "05:30",
            "content": "5 Rounds for Time",
            "stimulus": "Strength",
            "technical_cues": ["Breathe"],
        }

    def test_caption_defaults_to_empty_string(self) -> None:
        record = WorkoutRecord.from_dict(self._base())
        self.assertEqual("", record.caption)

    def test_caption_parsed_from_dict(self) -> None:
        data = {**self._base(), "caption": "Partner in pain — lean on each other."}
        record = WorkoutRecord.from_dict(data)
        self.assertEqual("Partner in pain — lean on each other.", record.caption)

    def test_caption_omitted_from_serialization_when_empty(self) -> None:
        record = WorkoutRecord.from_dict(self._base())
        self.assertNotIn("caption", record.to_dict())

    def test_caption_included_in_serialization_when_present(self) -> None:
        data = {**self._base(), "caption": "Chase the clock."}
        record = WorkoutRecord.from_dict(data)
        self.assertIn("caption", record.to_dict())
        self.assertEqual("Chase the clock.", record.to_dict()["caption"])

    def test_caption_title_case_key_normalizes(self) -> None:
        data = {**self._base(), "Caption": "Warm up well."}
        record = WorkoutRecord.from_dict(data)
        self.assertEqual("Warm up well.", record.caption)


if __name__ == "__main__":
    unittest.main()

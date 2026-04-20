from datetime import datetime, timezone
import unittest

from theassembly.models import CurrentState, WorkoutRecord
from theassembly.schedule import resolve_athlete_slate


class AthleteSlateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.current_state = CurrentState(status="open")
        self.today_record = WorkoutRecord.from_dict(
            {
                "date": "2026-04-20",
                "release_time": "23:30",
                "content": "5 rounds",
                "stimulus": "Aerobic pacing",
                "technical_cues": ["Stay smooth"],
            }
        )
        self.tomorrow_record = WorkoutRecord.from_dict(
            {
                "date": "2026-04-21",
                "release_time": "23:30",
                "content": "Tomorrow grinder",
                "stimulus": "Steady effort",
                "technical_cues": ["Stay patient"],
            }
        )

    def test_preview_window_shows_tomorrows_workout_after_4pm(self) -> None:
        # 4:30 PM ET is 20:30 UTC during EDT
        slate = resolve_athlete_slate(
            [self.today_record, self.tomorrow_record],
            self.current_state,
            datetime(2026, 4, 20, 20, 30, tzinfo=timezone.utc),
            "America/New_York",
        )

        self.assertEqual("open", slate.status)
        self.assertTrue(slate.is_preview)
        self.assertEqual("Tomorrow's Workout", slate.heading)
        self.assertEqual("2026-04-21", slate.workout.date if slate.workout else None)
        self.assertEqual("preview", slate.logic_window)

    def test_preview_window_respects_closed_repo_state(self) -> None:
        slate = resolve_athlete_slate(
            [self.today_record, self.tomorrow_record],
            CurrentState(status="closed"),
            datetime(2026, 4, 21, 0, 30, tzinfo=timezone.utc),
            "America/New_York",
        )

        self.assertEqual("closed", slate.status)
        self.assertEqual("The organizer has closed the current slate.", slate.message)

    def test_overnight_window_shows_todays_workout_at_six_am_even_before_release_time(self) -> None:
        slate = resolve_athlete_slate(
            [self.today_record, self.tomorrow_record],
            self.current_state,
            datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
            "America/New_York",
        )

        self.assertEqual("open", slate.status)
        self.assertFalse(slate.is_preview)
        self.assertEqual("overnight", slate.logic_window)
        self.assertEqual("2026-04-20", slate.workout.date if slate.workout else None)

    def test_overnight_window_stays_open_at_exactly_nine_am(self) -> None:
        slate = resolve_athlete_slate(
            [self.today_record, self.tomorrow_record],
            self.current_state,
            datetime(2026, 4, 20, 13, 0, tzinfo=timezone.utc),
            "America/New_York",
        )

        self.assertEqual("open", slate.status)
        self.assertFalse(slate.is_preview)
        self.assertEqual("Today's Workout", slate.heading)
        self.assertEqual("overnight", slate.logic_window)

    def test_overnight_window_at_seven_forty_am_maps_to_local_date(self) -> None:
        slate = resolve_athlete_slate(
            [self.today_record, self.tomorrow_record],
            self.current_state,
            datetime(2026, 4, 20, 11, 40, tzinfo=timezone.utc),
            "America/New_York",
        )

        self.assertEqual("open", slate.status)
        self.assertFalse(slate.is_preview)
        self.assertEqual("2026-04-20", slate.workout.date if slate.workout else None)
        self.assertEqual("overnight", slate.logic_window)

    def test_daytime_window_closes_at_nine_oh_one(self) -> None:
        slate = resolve_athlete_slate(
            [self.today_record, self.tomorrow_record],
            self.current_state,
            datetime(2026, 4, 20, 13, 1, tzinfo=timezone.utc),
            "America/New_York",
        )

        self.assertEqual("closed", slate.status)
        self.assertEqual("The slate is closed for the day. Check back at 4:00 PM ET.", slate.message)
        self.assertEqual("Mon Apr 20 at 4:00 PM", slate.next_release_label)
        self.assertEqual("closed", slate.logic_window)

    def test_preview_window_remains_closed_at_359_59_pm_et(self) -> None:
        # 3:59:59 PM ET is 19:59:59 UTC during EDT
        slate = resolve_athlete_slate(
            [self.today_record, self.tomorrow_record],
            self.current_state,
            datetime(2026, 4, 20, 19, 59, 59, tzinfo=timezone.utc),
            "America/New_York",
        )

        self.assertEqual("closed", slate.status)
        self.assertFalse(slate.is_preview)
        self.assertEqual("closed", slate.logic_window)

    def test_preview_window_opens_at_exactly_400_pm_et(self) -> None:
        # 4:00 PM ET is 20:00 UTC during EDT
        slate = resolve_athlete_slate(
            [self.today_record, self.tomorrow_record],
            self.current_state,
            datetime(2026, 4, 20, 20, 0, 0, tzinfo=timezone.utc),
            "America/New_York",
        )

        self.assertEqual("open", slate.status)
        self.assertTrue(slate.is_preview)
        self.assertEqual("Tomorrow's Workout", slate.heading)
        self.assertEqual("2026-04-21", slate.workout.date if slate.workout else None)
        self.assertEqual("preview", slate.logic_window)

    def test_preview_window_stays_open_at_400_01_pm_et(self) -> None:
        # 4:00:01 PM ET is 20:00:01 UTC during EDT
        slate = resolve_athlete_slate(
            [self.today_record, self.tomorrow_record],
            self.current_state,
            datetime(2026, 4, 20, 20, 0, 1, tzinfo=timezone.utc),
            "America/New_York",
        )

        self.assertEqual("open", slate.status)
        self.assertTrue(slate.is_preview)
        self.assertEqual("preview", slate.logic_window)

    def test_preview_window_reports_missing_tomorrow_workout(self) -> None:
        slate = resolve_athlete_slate(
            [self.today_record],
            self.current_state,
            datetime(2026, 4, 21, 0, 30, tzinfo=timezone.utc),
            "America/New_York",
        )

        self.assertEqual("closed", slate.status)
        self.assertEqual("Tomorrow's workout has not been staged yet.", slate.message)


if __name__ == "__main__":
    unittest.main()

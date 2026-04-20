import unittest

from theassembly.github_repo import GitHubDataRepository, GitHubRepoConfig
from theassembly.models import CurrentState, WorkoutRecord


class GitHubRepositoryTests(unittest.TestCase):
    def test_stage_workout_reopens_closed_state(self) -> None:
        record = WorkoutRecord.from_dict(
            {
                "date": "2026-04-20",
                "release_time": "05:30",
                "content": "Run 1 mile",
                "stimulus": "Benchmark pace",
                "technical_cues": ["Relax shoulders"],
            }
        )

        class FakeRepository(GitHubDataRepository):
            def __init__(self) -> None:
                super().__init__(
                    GitHubRepoConfig(
                        token="token",
                        owner="owner",
                        repo="repo",
                        workouts_file_path="workouts.json",
                        current_state_file_path="current_state.json",
                    )
                )
                self.saved_records = None
                self.saved_state = None

            def fetch_workouts(self):  # type: ignore[override]
                return [], "workouts-sha"

            def fetch_current_state(self):  # type: ignore[override]
                return CurrentState(status="closed"), "state-sha"

            def save_workouts(self, records, sha, message):  # type: ignore[override]
                self.saved_records = (records, sha, message)

            def save_current_state(self, state, sha, message):  # type: ignore[override]
                self.saved_state = (state, sha, message)

        repository = FakeRepository()
        repository.stage_workout_and_open_state(record)

        self.assertIsNotNone(repository.saved_records)
        self.assertEqual("workouts-sha", repository.saved_records[1])
        self.assertEqual("state-sha", repository.saved_state[1] if repository.saved_state else None)
        self.assertEqual("open", repository.saved_state[0].status if repository.saved_state else None)

    def test_stage_workout_skips_open_state_write(self) -> None:
        record = WorkoutRecord.from_dict(
            {
                "date": "2026-04-20",
                "release_time": "05:30",
                "content": "Run 1 mile",
                "stimulus": "Benchmark pace",
                "technical_cues": ["Relax shoulders"],
            }
        )

        class FakeRepository(GitHubDataRepository):
            def __init__(self) -> None:
                super().__init__(
                    GitHubRepoConfig(
                        token="token",
                        owner="owner",
                        repo="repo",
                        workouts_file_path="workouts.json",
                        current_state_file_path="current_state.json",
                    )
                )
                self.state_saves = 0

            def fetch_workouts(self):  # type: ignore[override]
                return [], "workouts-sha"

            def fetch_current_state(self):  # type: ignore[override]
                return CurrentState(status="open"), "state-sha"

            def save_workouts(self, records, sha, message):  # type: ignore[override]
                return None

            def save_current_state(self, state, sha, message):  # type: ignore[override]
                self.state_saves += 1

        repository = FakeRepository()
        repository.stage_workout_and_open_state(record)

        self.assertEqual(0, repository.state_saves)


if __name__ == "__main__":
    unittest.main()

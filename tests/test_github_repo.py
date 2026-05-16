import base64
import json
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from theassembly.github_repo import GitHubDataRepository, GitHubRepoConfig
from theassembly.models import CurrentState, PhotoRecord, WorkoutRecord


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


def _make_repo(photos_folder: str = "photos") -> GitHubDataRepository:
    return GitHubDataRepository(
        GitHubRepoConfig(
            token="tok",
            owner="owner",
            repo="repo",
            workouts_file_path="workouts.json",
            current_state_file_path="current_state.json",
            photos_folder_path=photos_folder,
        )
    )


def _make_dir_response(entries: list[dict]) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = entries
    return resp


def _make_file_response(raw_bytes: bytes, content_type: str = "image/jpeg") -> MagicMock:
    encoded = base64.b64encode(raw_bytes).decode()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"content": encoded, "sha": "abc123"}
    resp.raise_for_status.return_value = None
    return resp


class TestFetchPhotos(unittest.TestCase):
    def test_returns_empty_on_404(self) -> None:
        repo = _make_repo()
        not_found = MagicMock()
        not_found.status_code = 404
        with patch("requests.get", return_value=not_found):
            result = repo.fetch_photos(date(2026, 4, 27))
        self.assertEqual([], result)

    def test_returns_all_images_regardless_of_date_prefix(self) -> None:
        """Photos uploaded directly (no date prefix) are returned alongside prefixed ones."""
        repo = _make_repo()
        entries = [
            {"type": "file", "name": "2026-04-27-hero.jpg", "url": "https://api/hero"},
            {"type": "file", "name": "IMG_5041.jpg", "url": "https://api/other"},
        ]
        img_bytes = b"\xff\xd8\xff"  # minimal JPEG magic bytes
        dir_resp = _make_dir_response(entries)
        file_resp = _make_file_response(img_bytes)

        def fake_get(url, **kwargs):
            if "contents/photos" in url:
                return dir_resp
            return file_resp

        with patch("requests.get", side_effect=fake_get):
            result = repo.fetch_photos(date(2026, 4, 27))

        self.assertEqual(2, len(result))

    def test_data_uri_contains_base64_content(self) -> None:
        repo = _make_repo()
        img_bytes = b"\x89PNG\r\n"
        entries = [{"type": "file", "name": "2026-04-27-snap.png", "url": "https://api/snap"}]
        dir_resp = _make_dir_response(entries)
        file_resp = _make_file_response(img_bytes, content_type="image/png")

        def fake_get(url, **kwargs):
            if "contents/photos" in url:
                return dir_resp
            return file_resp

        with patch("requests.get", side_effect=fake_get):
            result = repo.fetch_photos(date(2026, 4, 27))

        self.assertEqual(1, len(result))
        self.assertIn("data:image/png;base64,", result[0].data_uri)
        decoded = base64.b64decode(result[0].data_uri.split(",", 1)[1])
        self.assertEqual(img_bytes, decoded)

    def test_caps_at_six_photos(self) -> None:
        repo = _make_repo()
        entries = [
            {"type": "file", "name": f"2026-04-27-photo{i:02d}.jpg", "url": f"https://api/p{i}"}
            for i in range(10)
        ]
        img_bytes = b"\xff\xd8\xff"
        dir_resp = _make_dir_response(entries)
        file_resp = _make_file_response(img_bytes)

        def fake_get(url, **kwargs):
            if "contents/photos" in url:
                return dir_resp
            return file_resp

        with patch("requests.get", side_effect=fake_get):
            result = repo.fetch_photos(date(2026, 4, 27))

        self.assertEqual(6, len(result))

    def test_skips_non_image_extensions(self) -> None:
        repo = _make_repo()
        entries = [
            {"type": "file", "name": "2026-04-27-notes.txt", "url": "https://api/notes"},
            {"type": "file", "name": "2026-04-27-photo.jpg", "url": "https://api/photo"},
        ]
        img_bytes = b"\xff\xd8\xff"
        dir_resp = _make_dir_response(entries)
        file_resp = _make_file_response(img_bytes)

        def fake_get(url, **kwargs):
            if "contents/photos" in url:
                return dir_resp
            return file_resp

        with patch("requests.get", side_effect=fake_get):
            result = repo.fetch_photos(date(2026, 4, 27))

        self.assertEqual(1, len(result))
        self.assertEqual("2026-04-27-photo.jpg", result[0].filename)


class TestFetchAiImage(unittest.TestCase):
    def test_returns_data_uri_when_inline_content_present(self) -> None:
        repo = _make_repo()
        raw = b"\x89PNG\r\n\x1a\n" + b"a" * 32
        encoded = base64.b64encode(raw).decode()

        contents_resp = MagicMock()
        contents_resp.status_code = 200
        contents_resp.json.return_value = {"content": encoded}

        with patch("requests.get", return_value=contents_resp):
            data_uri = repo.fetch_ai_image(date(2026, 5, 4))

        self.assertIsNotNone(data_uri)
        assert data_uri is not None
        self.assertTrue(data_uri.startswith("data:image/png;base64,"))
        self.assertEqual(raw, base64.b64decode(data_uri.split(",", 1)[1]))

    def test_falls_back_to_download_url_when_inline_content_missing(self) -> None:
        repo = _make_repo()
        raw = b"\x89PNG\r\n\x1a\n" + b"b" * 16

        contents_resp = MagicMock()
        contents_resp.status_code = 200
        contents_resp.json.return_value = {
            "content": "",
            "download_url": "https://raw.example.com/2026-05-04.png",
        }

        download_resp = MagicMock()
        download_resp.status_code = 200
        download_resp.content = raw

        with patch("requests.get", side_effect=[contents_resp, download_resp]):
            data_uri = repo.fetch_ai_image(date(2026, 5, 4))

        self.assertIsNotNone(data_uri)
        assert data_uri is not None
        self.assertTrue(data_uri.startswith("data:image/png;base64,"))
        self.assertEqual(raw, base64.b64decode(data_uri.split(",", 1)[1]))

    def test_returns_none_when_download_url_missing_and_no_inline_content(self) -> None:
        repo = _make_repo()

        contents_resp = MagicMock()
        contents_resp.status_code = 200
        contents_resp.json.return_value = {"content": ""}

        with patch("requests.get", return_value=contents_resp):
            data_uri = repo.fetch_ai_image(date(2026, 5, 4))

        self.assertIsNone(data_uri)


class TestFetchNutritionBaseline(unittest.TestCase):
    def test_returns_dict_when_inline_content_present(self) -> None:
        repo = _make_repo()
        payload = {
            "calorie_guidance": 2450,
            "protein_target_g": 180,
            "recipe_ideas": [],
        }
        encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode()

        contents_resp = MagicMock()
        contents_resp.status_code = 200
        contents_resp.json.return_value = {"content": encoded}

        with patch("requests.get", return_value=contents_resp):
            nutrition = repo.fetch_nutrition_baseline(date(2026, 5, 4))

        self.assertEqual(payload, nutrition)

    def test_prefers_photos_ai_nutrition_path(self) -> None:
        repo = _make_repo()
        payload = {
            "calorie_guidance": 2450,
            "protein_target_g": 180,
            "recipe_ideas": [],
        }
        encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode()

        contents_resp = MagicMock()
        contents_resp.status_code = 200
        contents_resp.json.return_value = {"content": encoded}

        with patch("requests.get", return_value=contents_resp) as mock_get:
            nutrition = repo.fetch_nutrition_baseline(date(2026, 5, 4))

        self.assertEqual(payload, nutrition)
        first_url = mock_get.call_args_list[0].args[0]
        self.assertIn("photos/ai/nutrition-baselines/2026-05-04.json", str(first_url))

    def test_falls_back_to_legacy_root_nutrition_path(self) -> None:
        repo = _make_repo()
        payload = {
            "calorie_guidance": 2300,
            "protein_target_g": 165,
            "recipe_ideas": [],
        }
        encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode()

        primary_not_found = MagicMock()
        primary_not_found.status_code = 404

        legacy_resp = MagicMock()
        legacy_resp.status_code = 200
        legacy_resp.json.return_value = {"content": encoded}

        with patch("requests.get", side_effect=[primary_not_found, legacy_resp]) as mock_get:
            nutrition = repo.fetch_nutrition_baseline(date(2026, 5, 4))

        self.assertEqual(payload, nutrition)
        first_url = mock_get.call_args_list[0].args[0]
        second_url = mock_get.call_args_list[1].args[0]
        self.assertIn("photos/ai/nutrition-baselines/2026-05-04.json", str(first_url))
        self.assertIn("nutrition-baselines/2026-05-04.json", str(second_url))

    def test_falls_back_to_download_url_when_inline_content_missing(self) -> None:
        repo = _make_repo()
        payload = {
            "calorie_guidance": 2300,
            "protein_target_g": 165,
            "recipe_ideas": [],
        }

        contents_resp = MagicMock()
        contents_resp.status_code = 200
        contents_resp.json.return_value = {
            "content": "",
            "download_url": "https://raw.example.com/2026-05-04.json",
        }

        download_resp = MagicMock()
        download_resp.status_code = 200
        download_resp.content = json.dumps(payload).encode("utf-8")

        with patch("requests.get", side_effect=[contents_resp, download_resp]):
            nutrition = repo.fetch_nutrition_baseline(date(2026, 5, 4))

        self.assertEqual(payload, nutrition)

    def test_returns_none_when_missing(self) -> None:
        repo = _make_repo()
        not_found = MagicMock()
        not_found.status_code = 404

        with patch("requests.get", side_effect=[not_found, not_found]):
            nutrition = repo.fetch_nutrition_baseline(date(2026, 5, 4))

        self.assertIsNone(nutrition)

    def test_returns_none_for_invalid_json(self) -> None:
        repo = _make_repo()
        encoded = base64.b64encode(b"not json").decode()

        contents_resp = MagicMock()
        contents_resp.status_code = 200
        contents_resp.json.return_value = {"content": encoded}

        with patch("requests.get", return_value=contents_resp):
            nutrition = repo.fetch_nutrition_baseline(date(2026, 5, 4))

        self.assertIsNone(nutrition)


if __name__ == "__main__":
    unittest.main()

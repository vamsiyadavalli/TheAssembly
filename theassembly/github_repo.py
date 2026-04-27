from __future__ import annotations

import base64
import io
import mimetypes
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import quote

import requests

from theassembly.models import CurrentState, PhotoRecord, WorkoutRecord, load_current_state, load_workouts, serialize_current_state, serialize_workouts

try:
    from PIL import Image as _PILImage
    _PILLOW_AVAILABLE = True
except ImportError:
    _PILLOW_AVAILABLE = False


@dataclass(frozen=True)
class GitHubRepoConfig:
    token: str
    owner: str
    repo: str
    workouts_file_path: str
    current_state_file_path: str
    branch: str = "main"
    api_base: str = "https://api.github.com"
    photos_folder_path: str = "photos"


def build_text_update_payload(
    text_content: str,
    message: str,
    sha: str | None,
    branch: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(text_content.encode("utf-8")).decode("utf-8"),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha
    return payload


def build_update_payload(
    records: list[WorkoutRecord],
    message: str,
    sha: str | None,
    branch: str,
) -> dict[str, Any]:
    return build_text_update_payload(serialize_workouts(records), message=message, sha=sha, branch=branch)


@dataclass(frozen=True)
class GitHubFile:
    text: str
    sha: str | None


class GitHubDataRepository:
    def __init__(self, config: GitHubRepoConfig) -> None:
        self.config = config

    def _contents_url(self, file_path: str) -> str:
        quoted_path = quote(file_path.strip("/"))
        return f"{self.config.api_base}/repos/{self.config.owner}/{self.config.repo}/contents/{quoted_path}"

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.config.token}",
            "User-Agent": "TheAssembly",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request_json(self, method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = requests.request(
                method,
                url,
                headers=self._headers(),
                json=payload,
                timeout=30,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"GitHub API request failed: {exc}") from exc

        if response.status_code >= 400:
            raise RuntimeError(f"GitHub API request failed ({response.status_code}): {response.text}")

        return response.json() if response.text else {}

    def _fetch_file(self, file_path: str, missing_ok: bool = False) -> GitHubFile | None:
        url = self._contents_url(file_path)
        try:
            response = requests.get(
                url,
                headers=self._headers(),
                params={"ref": self.config.branch},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"GitHub API request failed: {exc}") from exc

        if response.status_code == 404 and missing_ok:
            return None

        if response.status_code >= 400:
            raise RuntimeError(f"GitHub API request failed ({response.status_code}): {response.text}")

        payload = response.json()
        encoded_content = payload.get("content", "")
        decoded_content = base64.b64decode(encoded_content).decode("utf-8") if encoded_content else ""
        return GitHubFile(text=decoded_content, sha=payload.get("sha"))

    def _save_file(self, file_path: str, text_content: str, sha: str | None, message: str) -> None:
        payload = build_text_update_payload(text_content, message=message, sha=sha, branch=self.config.branch)
        self._request_json("PUT", self._contents_url(file_path), payload)

    def fetch_workouts(self) -> tuple[list[WorkoutRecord], str | None]:
        file_data = self._fetch_file(self.config.workouts_file_path, missing_ok=True)
        if file_data is None:
            return [], None
        return load_workouts(file_data.text), file_data.sha

    def fetch_current_state(self) -> tuple[CurrentState, str | None]:
        file_data = self._fetch_file(self.config.current_state_file_path)
        if file_data is None:
            raise RuntimeError("current_state.json is missing from the configured repository.")
        return load_current_state(file_data.text), file_data.sha

    def save_workouts(self, records: list[WorkoutRecord], sha: str | None, message: str) -> None:
        self._save_file(self.config.workouts_file_path, serialize_workouts(records), sha=sha, message=message)

    def save_current_state(self, state: CurrentState, sha: str | None, message: str) -> None:
        self._save_file(
            self.config.current_state_file_path,
            serialize_current_state(state),
            sha=sha,
            message=message,
        )

    def upsert_workout(self, new_record: WorkoutRecord) -> None:
        records, sha = self.fetch_workouts()
        record_map = {record.date: record for record in records}
        record_map[new_record.date] = new_record
        updated_records = sorted(record_map.values(), key=lambda record: (record.date, record.release_time))
        self.save_workouts(updated_records, sha=sha, message=f"Stage workout for {new_record.date}")

    def stage_workout_and_open_state(self, new_record: WorkoutRecord) -> None:
        records, workouts_sha = self.fetch_workouts()
        current_state, state_sha = self.fetch_current_state()

        record_map = {record.date: record for record in records}
        record_map[new_record.date] = new_record
        updated_records = sorted(record_map.values(), key=lambda record: (record.date, record.release_time))
        self.save_workouts(updated_records, sha=workouts_sha, message=f"Stage workout for {new_record.date}")

        if current_state.status == "open":
            return

        try:
            self.save_current_state(CurrentState(status="open"), sha=state_sha, message="Reopen athlete slate")
        except RuntimeError as exc:
            raise RuntimeError(f"Workout saved, but current_state.json reset failed: {exc}") from exc

    _MAX_PHOTOS = 6
    _ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}

    def fetch_photos(self, target_date: date) -> list[PhotoRecord]:
        """Return up to 6 PhotoRecords for the given date from the photos folder.

        Returns an empty list on any error (non-blocking).
        """
        prefix = target_date.isoformat()
        url = self._contents_url(self.config.photos_folder_path)
        try:
            response = requests.get(
                url,
                headers=self._headers(),
                params={"ref": self.config.branch},
                timeout=30,
            )
        except requests.RequestException:
            return []

        if response.status_code == 404:
            return []
        if response.status_code >= 400:
            return []

        entries = response.json()
        if not isinstance(entries, list):
            return []

        matched = []
        for entry in entries:
            name: str = entry.get("name", "")
            ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if entry.get("type") != "file":
                continue
            if not name.startswith(prefix):
                continue
            if ext not in self._ALLOWED_EXTENSIONS:
                continue
            matched.append(entry)

        matched.sort(key=lambda e: e["name"])
        matched = matched[: self._MAX_PHOTOS]

        records: list[PhotoRecord] = []
        for entry in matched:
            try:
                file_response = requests.get(
                    entry["url"],
                    headers=self._headers(),
                    params={"ref": self.config.branch},
                    timeout=30,
                )
                file_response.raise_for_status()
                file_data = file_response.json()
                raw_content = file_data.get("content", "").replace("\n", "").strip()
                raw_bytes = base64.b64decode(raw_content)

                if _PILLOW_AVAILABLE:
                    try:
                        buf = io.BytesIO(raw_bytes)
                        img = _PILImage.open(buf).convert("RGB")
                        max_side = 800
                        w, h = img.size
                        if max(w, h) > max_side:
                            scale = max_side / max(w, h)
                            img = img.resize((int(w * scale), int(h * scale)), _PILImage.LANCZOS)
                        out = io.BytesIO()
                        img.save(out, format="JPEG", quality=70, optimize=True)
                        raw_bytes = out.getvalue()
                        mime = "image/jpeg"
                    except Exception:
                        mime = mimetypes.guess_type(entry["name"])[0] or "image/jpeg"
                else:
                    mime = mimetypes.guess_type(entry["name"])[0] or "image/jpeg"

                data_uri = f"data:{mime};base64,{base64.b64encode(raw_bytes).decode()}"
                records.append(PhotoRecord(filename=entry["name"], data_uri=data_uri, date_str=prefix))
            except Exception:
                continue

        return records

    def upload_photo(self, date_str: str, original_filename: str, content_bytes: bytes) -> None:
        """Upload a photo to the photos folder, naming it {date_str}-{original_filename}."""
        safe_name = original_filename.replace("/", "_").replace("..", "_")
        dest_path = f"{self.config.photos_folder_path}/{date_str}-{safe_name}"
        encoded = base64.b64encode(content_bytes).decode("utf-8")
        payload: dict[str, Any] = {
            "message": f"Add workout photo {date_str}",
            "content": encoded,
            "branch": self.config.branch,
        }

        url = self._contents_url(dest_path)
        # Check if file already exists so we can pass its SHA for an update.
        try:
            check_response = requests.get(url, headers=self._headers(), timeout=30)
            if check_response.status_code == 200:
                existing_sha = check_response.json().get("sha")
                if existing_sha:
                    payload["sha"] = existing_sha
        except requests.RequestException:
            pass

        self._request_json("PUT", url, payload)


GitHubWorkoutsRepository = GitHubDataRepository

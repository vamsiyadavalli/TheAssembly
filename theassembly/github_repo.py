from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests

from theassembly.models import CurrentState, WorkoutRecord, load_current_state, load_workouts, serialize_current_state, serialize_workouts


@dataclass(frozen=True)
class GitHubRepoConfig:
    token: str
    owner: str
    repo: str
    workouts_file_path: str
    current_state_file_path: str
    branch: str = "main"
    api_base: str = "https://api.github.com"


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


GitHubWorkoutsRepository = GitHubDataRepository

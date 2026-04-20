from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class AppConfig:
    github_token: str | None
    workouts_repo_owner: str | None
    workouts_repo_name: str | None
    workouts_file_path: str
    current_state_file_path: str
    workouts_repo_branch: str
    admin_password: str | None
    timezone_name: str

    @property
    def github_enabled(self) -> bool:
        return bool(self.github_token and self.workouts_repo_owner and self.workouts_repo_name)

    @property
    def admin_enabled(self) -> bool:
        return bool(self.admin_password)


def _lookup_setting(name: str, secrets: Mapping[str, Any] | None, default: str | None = None) -> str | None:
    env_value = os.getenv(name)
    if env_value is not None:
        return env_value

    if secrets is not None and name in secrets:
        value = secrets[name]
        return str(value) if value is not None else default

    return default


def load_config(secrets: Mapping[str, Any] | None = None) -> AppConfig:
    return AppConfig(
        github_token=_lookup_setting("GITHUB_TOKEN", secrets),
        workouts_repo_owner=_lookup_setting("WORKOUTS_REPO_OWNER", secrets),
        workouts_repo_name=_lookup_setting("WORKOUTS_REPO_NAME", secrets),
        workouts_file_path=_lookup_setting("WORKOUTS_FILE_PATH", secrets, "workouts.json") or "workouts.json",
        current_state_file_path=_lookup_setting("CURRENT_STATE_FILE_PATH", secrets, "current_state.json")
        or "current_state.json",
        workouts_repo_branch=_lookup_setting("WORKOUTS_REPO_BRANCH", secrets, "main") or "main",
        admin_password=_lookup_setting("ADMIN_PASSWORD", secrets),
        timezone_name=_lookup_setting("APP_TIMEZONE", secrets, "America/New_York") or "America/New_York",
    )

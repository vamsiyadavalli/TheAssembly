from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
import json
import re
from typing import Any, Iterable


REQUIRED_FIELDS = {"date", "release_time", "stimulus", "technical_cues"}
VALID_STATE_VALUES = {"open", "closed"}


def _normalize_key(key: str) -> str:
    return re.sub(r"[\s\-]+", "_", key.strip().lower())


def _normalize_cues(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(line.strip() for line in value.splitlines() if line.strip())

    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())

    raise ValueError("technical_cues must be a list of strings or a newline-delimited string.")


@dataclass(frozen=True)
class WorkoutRecord:
    date: str
    release_time: str
    workout_content: str
    stimulus: str
    technical_cues: tuple[str, ...]
    status: str = "scheduled"

    @property
    def workout_date(self) -> date:
        return date.fromisoformat(self.date)

    @property
    def release_clock(self) -> time:
        return time.fromisoformat(self.release_time)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkoutRecord":
        normalized = {_normalize_key(key): value for key, value in payload.items()}
        missing = REQUIRED_FIELDS.difference(normalized)
        if missing:
            raise ValueError(f"Workout record is missing required fields: {', '.join(sorted(missing))}")

        workout_content = normalized.get("content", normalized.get("workout_content"))
        if workout_content is None:
            raise ValueError("Workout record is missing required field: content")

        record = cls(
            date=str(normalized["date"]).strip(),
            release_time=str(normalized["release_time"]).strip(),
            workout_content=str(workout_content).strip(),
            stimulus=str(normalized["stimulus"]).strip(),
            technical_cues=_normalize_cues(normalized["technical_cues"]),
            status=str(normalized.get("status", "scheduled")).strip() or "scheduled",
        )

        _ = record.workout_date
        _ = record.release_clock
        return record

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "release_time": self.release_time,
            "content": self.workout_content,
            "stimulus": self.stimulus,
            "technical_cues": list(self.technical_cues),
            "status": self.status,
        }


@dataclass(frozen=True)
class CurrentState:
    status: str

    @property
    def is_open(self) -> bool:
        return self.status == "open"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CurrentState":
        normalized = {_normalize_key(key): value for key, value in payload.items()}
        raw_status = str(normalized.get("status", "")).strip().lower()
        if raw_status not in VALID_STATE_VALUES:
            raise ValueError("current_state.json status must be 'open' or 'closed'.")
        return cls(status=raw_status)

    def to_dict(self) -> dict[str, str]:
        return {"status": self.status}


def ensure_unique_dates(records: Iterable[WorkoutRecord]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for record in records:
        if record.date in seen:
            duplicates.add(record.date)
        seen.add(record.date)

    if duplicates:
        raise ValueError(f"Duplicate workout dates are not allowed: {', '.join(sorted(duplicates))}")


def load_workouts(raw_text: str) -> list[WorkoutRecord]:
    if not raw_text.strip():
        return []

    payload = json.loads(raw_text)
    if isinstance(payload, dict):
        payload = payload.get("workouts", [])

    if not isinstance(payload, list):
        raise ValueError("workouts.json must contain a list of workout records.")

    records = [WorkoutRecord.from_dict(item) for item in payload]
    ensure_unique_dates(records)
    return sorted(records, key=lambda record: (record.date, record.release_time))


def serialize_workouts(records: Iterable[WorkoutRecord]) -> str:
    ordered_records = sorted(records, key=lambda record: (record.date, record.release_time))
    ensure_unique_dates(ordered_records)
    return json.dumps([record.to_dict() for record in ordered_records], indent=2) + "\n"


def load_current_state(raw_text: str) -> CurrentState:
    payload = json.loads(raw_text)
    if not isinstance(payload, dict):
        raise ValueError("current_state.json must contain a JSON object.")
    return CurrentState.from_dict(payload)


def serialize_current_state(state: CurrentState) -> str:
    return json.dumps(state.to_dict(), indent=2) + "\n"

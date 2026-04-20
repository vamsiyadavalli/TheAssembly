from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import pytz

from theassembly.models import CurrentState, WorkoutRecord

APP_TIMEZONE_NAME = "America/New_York"
APP_TIMEZONE = pytz.timezone(APP_TIMEZONE_NAME)
PREVIEW_START_TIME = time(hour=16, minute=0)
DAYTIME_CLOSE_START = time(hour=9, minute=1)


@dataclass(frozen=True)
class AthleteSlate:
    status: str
    heading: str
    message: str
    workout: WorkoutRecord | None = None
    next_release_label: str | None = None
    is_preview: bool = False
    logic_window: str = "closed"


def _to_local(now: datetime, timezone_name: str) -> datetime:
    timezone = pytz.timezone(timezone_name)
    if now.tzinfo is None:
        return timezone.localize(now)
    return now.astimezone(timezone)


def _format_release_label(release_at: datetime) -> str:
    month_and_day = release_at.strftime("%a %b %d").replace(" 0", " ")
    hour_and_time = release_at.strftime("%I:%M %p").lstrip("0")
    return f"{month_and_day} at {hour_and_time}"


def _next_release_label(
    records: list[WorkoutRecord],
    now_local: datetime,
    daytime_close_start: time,
    preview_start_time: time,
) -> str | None:
    zone = now_local.tzinfo
    if zone is None:
        return None

    upcoming = []
    for record in records:
        if record.status == "archived":
            continue

        preview_at = zone.localize(datetime.combine(record.workout_date - timedelta(days=1), preview_start_time))
        next_preview_at = zone.localize(datetime.combine(record.workout_date, preview_start_time))

        if now_local < preview_at:
            upcoming.append(preview_at)
            continue

        if record.workout_date == now_local.date() and now_local.time() >= daytime_close_start and now_local < next_preview_at:
            upcoming.append(next_preview_at)

    if not upcoming:
        return None

    return _format_release_label(min(upcoming))


def detect_logic_window(
    now_local: datetime,
    daytime_close_start: time = DAYTIME_CLOSE_START,
    preview_start_time: time = PREVIEW_START_TIME,
) -> tuple[str, date | None, bool]:
    local_date = now_local.date()
    local_time = now_local.time().replace(tzinfo=None)

    if local_time >= preview_start_time:
        return "preview", now_local.date() + timedelta(days=1), True

    overnight_start = time(0, 0)
    overnight_end = time(9, 0)
    if overnight_start <= local_time <= overnight_end:
        return "overnight", local_date, False

    if local_time >= daytime_close_start:
        return "closed", None, False

    return "overnight", now_local.date(), False


def resolve_athlete_slate(
    records: list[WorkoutRecord],
    current_state: CurrentState,
    now: datetime,
    timezone_name: str,
    wipe_time: time = DAYTIME_CLOSE_START,
    preview_time: time = PREVIEW_START_TIME,
) -> AthleteSlate:
    now_local = _to_local(now, timezone_name)
    next_release_label = _next_release_label(records, now_local, wipe_time, preview_time)
    logic_window, target_date, is_preview = detect_logic_window(now_local, wipe_time, preview_time)

    if logic_window == "closed":
        return AthleteSlate(
            status="closed",
            heading="Garage Closed",
            message="The slate is closed for the day. Check back at 4:00 PM ET.",
            next_release_label=next_release_label,
            logic_window=logic_window,
        )

    if not current_state.is_open:
        return AthleteSlate(
            status="closed",
            heading="Garage Closed",
            message="The organizer has closed the current slate.",
            next_release_label=next_release_label,
            logic_window=logic_window,
        )

    target_records = [
        record for record in records if record.workout_date == target_date and record.status != "archived"
    ]
    if not target_records:
        return AthleteSlate(
            status="closed",
            heading="Garage Closed",
            message="Tomorrow's workout has not been staged yet." if is_preview else "No workout is live right now.",
            next_release_label=next_release_label,
            logic_window=logic_window,
        )

    target_record = min(target_records, key=lambda record: record.release_time)

    return AthleteSlate(
        status="open",
        heading="Tomorrow's Workout" if is_preview else "Today's Workout",
        message="Preview is live." if is_preview else "Current workout is live.",
        workout=target_record,
        next_release_label=next_release_label,
        is_preview=is_preview,
        logic_window=logic_window,
    )

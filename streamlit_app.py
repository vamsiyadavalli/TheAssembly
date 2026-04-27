from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
import hmac
import os
import re

import pytz
import streamlit as st

from theassembly.github_repo import GitHubDataRepository, GitHubRepoConfig
from theassembly.hn_topics import HNConversationStarter, fetch_hn_conversation_starter
from theassembly.models import CurrentState, WorkoutRecord, load_current_state, load_workouts
from theassembly.schedule import AthleteSlate, resolve_athlete_slate
from theassembly.weather import WorkoutWeather, fetch_workout_weather
from theassembly.workout_formatting import format_workout_html, format_workout_summary


CUSTOM_CSS = """
<style>
    .stApp {
        background:
            radial-gradient(circle at top, rgba(249, 115, 22, 0.14), transparent 35%),
            linear-gradient(180deg, #050816 0%, #020617 100%);
    }
    .hero-card, .panel-card {
        border: 1px solid rgba(248, 250, 252, 0.08);
        background: rgba(15, 23, 42, 0.88);
        border-radius: 20px;
        padding: 1.2rem;
        box-shadow: 0 10px 30px rgba(2, 6, 23, 0.35);
    }
    .hero-title {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.35rem;
    }
    .eyebrow {
        color: #fb923c;
        letter-spacing: 0.16em;
        font-size: 0.78rem;
        text-transform: uppercase;
    }
    .garage-closed {
        font-size: 2rem;
        font-weight: 700;
        margin: 0.6rem 0 0.4rem;
    }
    .workout-block {
        font-size: 1.1rem;
        line-height: 1.6;
        white-space: pre-wrap;
    }
    .cue-chip {
        display: inline-block;
        margin: 0.2rem 0.35rem 0.2rem 0;
        padding: 0.3rem 0.7rem;
        border-radius: 999px;
        border: 1px solid rgba(251, 146, 60, 0.28);
        background: rgba(251, 146, 60, 0.08);
    }
    .section-label {
        font-size: 0.85rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 0.45rem;
    }
    .clothing-rec {
        border-left: 3px solid rgba(251, 146, 60, 0.6);
        padding: 0.5rem 0.8rem;
        font-size: 0.9rem;
        line-height: 1.55;
        color: #e2e8f0;
        margin-top: 0.75rem;
    }
    /* ---- Layout: reduce Streamlit default padding ---- */
    .stMainBlockContainer {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        padding-top: 1.5rem !important;
    }
    /* ---- Responsive 2-col grid ---- */
    .page-grid {
        display: grid;
        grid-template-columns: 1fr 300px;
        gap: 1rem;
        align-items: start;
        max-width: 1040px;
        margin: 0 auto;
    }
    @media (max-width: 720px) {
        .page-grid { grid-template-columns: 1fr; }
    }
    .col-main > * + * { margin-top: 0.75rem; }
    .col-side > * + * { margin-top: 0.75rem; }
    /* ---- Weather strip ---- */
    .weather-section-label {
        font-size: 0.72rem;
        font-weight: 700;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 0.5rem;
    }
    .weather-strip {
        display: flex;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        gap: 0.4rem;
        padding-bottom: 0.25rem;
        scrollbar-width: none;
    }
    .weather-strip::-webkit-scrollbar { display: none; }
    .wh-card {
        min-width: 68px;
        flex-shrink: 0;
        text-align: center;
        padding: 0.4rem 0.3rem;
        background: rgba(248, 250, 252, 0.04);
        border-radius: 8px;
        border: 1px solid rgba(248, 250, 252, 0.06);
    }
    .wh-time {
        font-size: 0.7rem;
        font-weight: 700;
        color: #fb923c;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .wh-temp {
        font-size: 1rem;
        font-weight: 700;
        margin: 0.2rem 0;
    }
    .wh-meta {
        font-size: 0.7rem;
        color: #94a3b8;
        line-height: 1.5;
    }
    /* ---- Structured movements ---- */
    .workout-structured-header {
        font-size: 1.05rem;
        font-weight: 700;
        color: #e2e8f0;
        margin-bottom: 0.6rem;
    }
    .workout-legacy {
        font-size: 1.05rem;
        line-height: 1.65;
        white-space: pre-wrap;
        color: #e2e8f0;
    }
    .movement-list {
        display: flex;
        flex-direction: column;
        gap: 0;
    }
    .movement-row {
        padding: 0.55rem 0;
        border-bottom: 1px solid rgba(248, 250, 252, 0.06);
    }
    .movement-row:last-child { border-bottom: none; }
    .movement-row-main {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.5rem;
    }
    .movement-row-left {
        display: flex;
        align-items: baseline;
        gap: 0.45rem;
        flex: 1;
        min-width: 0;
    }
    .mvmt-reps {
        font-weight: 700;
        color: #fb923c;
        white-space: nowrap;
        flex-shrink: 0;
    }
    .mvmt-name {
        font-weight: 600;
        color: #e2e8f0;
    }
    .movement-badges {
        display: flex;
        gap: 0.35rem;
        flex-shrink: 0;
    }
    .mvmt-notes {
        color: #64748b;
        font-size: 0.85rem;
        margin-top: 0.15rem;
    }
    .movement-finisher-block {
        margin-top: 1rem;
        padding: 0.75rem 0.9rem;
        border-radius: 10px;
        background: rgba(245, 158, 11, 0.07);
        border: 1px solid rgba(245, 158, 11, 0.2);
    }
    .movement-section-label {
        font-size: 0.72rem;
        font-weight: 700;
        color: #f59e0b;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        margin-bottom: 0.5rem;
    }
    .rx-badge {
        display: inline-block;
        padding: 0.15rem 0.5rem;
        border-radius: 5px;
        background: rgba(16, 185, 129, 0.18);
        border: 1px solid rgba(16, 185, 129, 0.4);
        color: #6ee7b7;
        font-size: 0.82rem;
        font-weight: 600;
        white-space: nowrap;
    }
    .scaled-badge {
        display: inline-block;
        padding: 0.15rem 0.5rem;
        border-radius: 5px;
        background: rgba(245, 158, 11, 0.15);
        border: 1px solid rgba(245, 158, 11, 0.35);
        color: #fcd34d;
        font-size: 0.82rem;
        font-weight: 600;
        white-space: nowrap;
    }
</style>
"""


AppRole = Literal["athlete", "admin"]

_DEFAULT_GYM_LAT = 39.3448   # Oakdale High School, Ijamsville MD
_DEFAULT_GYM_LON = -77.3241


@dataclass
class AppConfig:
    github_enabled: bool
    github_token: str | None
    workouts_repo_owner: str
    workouts_repo_name: str
    workouts_repo_branch: str
    workouts_file_path: str
    current_state_file_path: str
    app_timezone: str
    app_role: AppRole
    admin_password: str | None
    admin_enabled: bool
    gym_lat: float
    gym_lon: float


def _secret_or_env(key: str, default: str | None = None) -> str | None:
    if key in st.secrets:
        value = st.secrets.get(key)
        return str(value) if value is not None else default
    return os.getenv(key, default)


def _normalize_token(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None

    value = raw_value.strip()
    if not value:
        return None

    if value.startswith("github_pat_") or value.startswith("ghp_"):
        return value

    # Guard against accidental labels like "read write: github_pat_..." pasted in secrets.
    match = re.search(r"(github_pat_[A-Za-z0-9_]+|ghp_[A-Za-z0-9]+)", value)
    if match:
        return match.group(1)

    return value


def _token_for_role(app_role: AppRole) -> str | None:
    if app_role == "admin":
        return _normalize_token(_secret_or_env("GITHUB_WRITE_TOKEN") or _secret_or_env("GITHUB_TOKEN"))
    return _normalize_token(_secret_or_env("GITHUB_READ_TOKEN") or _secret_or_env("GITHUB_TOKEN"))


def _friendly_bridge_error(raw_error: str, config: AppConfig) -> str:
    if "GitHub API request failed (401)" in raw_error:
        return (
            "GitHub authentication failed (401). Check that your token is valid and not expired, "
            "and that GITHUB_WRITE_TOKEN is set correctly for admin mode."
        )

    if "GitHub API request failed (404)" in raw_error:
        return (
            "GitHub data was not found (404). Verify repo access and settings: "
            f"owner={config.workouts_repo_owner}, repo={config.workouts_repo_name}, "
            f"branch={config.workouts_repo_branch}, workouts_path={config.workouts_file_path}, "
            f"state_path={config.current_state_file_path}. A PAT without repo access can also surface as 404."
        )

    return raw_error


def _app_config(app_role: AppRole = "athlete") -> AppConfig:
    github_token = _token_for_role(app_role)
    owner = _secret_or_env("WORKOUTS_REPO_OWNER", "") or ""
    repo = _secret_or_env("WORKOUTS_REPO_NAME", "") or ""
    admin_password = _secret_or_env("ADMIN_PASSWORD")

    github_enabled = bool(github_token and owner and repo)

    def _parse_coord(key: str, default: float) -> float:
        raw = _secret_or_env(key)
        try:
            return float(raw) if raw is not None else default
        except ValueError:
            return default

    return AppConfig(
        github_enabled=github_enabled,
        github_token=github_token,
        workouts_repo_owner=owner,
        workouts_repo_name=repo,
        workouts_repo_branch=_secret_or_env("WORKOUTS_REPO_BRANCH", "main") or "main",
        workouts_file_path=_secret_or_env("WORKOUTS_FILE_PATH", "workouts.json") or "workouts.json",
        current_state_file_path=_secret_or_env("CURRENT_STATE_FILE_PATH", "current_state.json") or "current_state.json",
        app_timezone=_secret_or_env("APP_TIMEZONE", "America/New_York") or "America/New_York",
        app_role=app_role,
        admin_password=admin_password,
        admin_enabled=bool(admin_password),
        gym_lat=_parse_coord("GYM_LAT", 39.3448),
        gym_lon=_parse_coord("GYM_LON", -77.3241),
    )


def _build_repository(config: AppConfig) -> GitHubDataRepository | None:
    if not config.github_enabled:
        return None

    repo_config = GitHubRepoConfig(
        token=config.github_token or "",
        owner=config.workouts_repo_owner or "",
        repo=config.workouts_repo_name or "",
        workouts_file_path=config.workouts_file_path,
        current_state_file_path=config.current_state_file_path,
        branch=config.workouts_repo_branch,
    )
    return GitHubDataRepository(repo_config)


def _load_data(config: AppConfig) -> tuple[list[WorkoutRecord], CurrentState, str | None]:
    repository = _build_repository(config)
    if repository is None:
        # Local dev fallback: use sibling TheAssemblyData repo when secrets are not configured.
        base_dir = Path(__file__).resolve().parent
        local_data_dir = base_dir.parent / "TheAssemblyData"
        workouts_path = local_data_dir / config.workouts_file_path
        state_path = local_data_dir / config.current_state_file_path

        try:
            records = load_workouts(workouts_path.read_text(encoding="utf-8"))
            current_state = load_current_state(state_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            return [], CurrentState(status="closed"), (
                "GitHub access is not configured yet, and local fallback files were not found "
                f"under {local_data_dir}: {exc}"
            )
        except ValueError as exc:
            return [], CurrentState(status="closed"), f"Local fallback data is invalid: {exc}"

        return records, current_state, (
            f"Using local fallback data from {local_data_dir} because GitHub access is not configured."
        )

    try:
        records, _ = repository.fetch_workouts()
        current_state, _ = repository.fetch_current_state()
    except RuntimeError as exc:
        return [], CurrentState(status="closed"), _friendly_bridge_error(str(exc), config)

    return records, current_state, None


@st.cache_data(ttl=1800)
def _cached_fetch_weather(
    lat: float,
    lon: float,
    target_date_iso: str,
    timezone_name: str,
) -> WorkoutWeather | None:
    from datetime import date as _date
    target = _date.fromisoformat(target_date_iso)
    return fetch_workout_weather(lat, lon, target, timezone_name)


@st.cache_data(ttl=3600)
def _cached_fetch_hn_conversation_starter() -> HNConversationStarter | None:
    return fetch_hn_conversation_starter()


def _build_weather_html(weather: WorkoutWeather | None) -> str:
    """Return a self-contained HTML string for the weather side panel."""
    if weather is None:
        return '<div class="panel-card"><span style="color:#64748b">Weather unavailable.</span></div>'

    cards = ""
    for hw in weather.hours:
        label = f"{hw.hour}am" if hw.hour < 12 else f"{hw.hour - 12 if hw.hour > 12 else hw.hour}pm"
        cards += (
            f'<div class="wh-card">'
            f'<div class="wh-time">{label}</div>'
            f'<div class="wh-temp">{hw.temperature:.0f}°</div>'
            f'<div class="wh-meta">feels {hw.feels_like:.0f}°<br>'
            f'{hw.condition}<br>'
            f'💨{hw.wind_speed:.0f}<br>'
            f'💧{hw.precip_probability}%</div>'
            f'</div>'
        )

    return (
        f'<div class="panel-card">'
        f'<div class="weather-section-label">Dress for the Session · 5–8am</div>'
        f'<div class="weather-strip">{cards}</div>'
        f'<div class="clothing-rec">{weather.clothing_recommendation}</div>'
        f'</div>'
    )


def _build_hn_html(starter: HNConversationStarter | None) -> str:
    """Return a self-contained HTML string for the HN conversation starter."""
    if starter is None:
        return '<span style="color:#94a3b8">Trending topics are unavailable right now.</span>'

    topic_markup = "".join(
        (
            f'<div style="margin-bottom:0.45rem">'
            f'<strong>#{idx}.</strong> '
            f'<a href="{topic.display_url}" target="_blank" style="color:#e2e8f0;text-decoration:underline">{topic.title}</a> '
            f'<span style="color:#94a3b8">({topic.points} pts · {topic.comments} comments)</span>'
            f'</div>'
        )
        for idx, topic in enumerate(starter.top_topics, start=1)
    )

    return (
        f'<div style="font-weight:700;margin-bottom:0.45rem;color:#fb923c">Top 3 HN Topics Right Now</div>'
        f'{topic_markup}'
        f'<div style="margin:0.75rem 0 0.35rem;font-weight:700">Most Engaging Discussion</div>'
        f'<div style="margin-bottom:0.4rem"><a href="{starter.selected_topic.hn_link}" target="_blank" style="color:#e2e8f0;text-decoration:underline">{starter.selected_topic.title}</a></div>'
        f'<div style="color:#cbd5e1;line-height:1.55">{starter.summary}</div>'
        f'<div style="margin-top:0.6rem;color:#64748b;font-size:0.78rem">Refreshed: {starter.refreshed_at_utc}</div>'
    )


def _render_athlete_view(slate: AthleteSlate, config: AppConfig) -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.title("TheAssembly")

    # Pre-fetch both async data sources before building HTML.
    conversation_starter = _cached_fetch_hn_conversation_starter()

    if slate.status == "open" and slate.workout is not None:
        workout = slate.workout
        weather_date = workout.workout_date.isoformat()
        weather = _cached_fetch_weather(config.gym_lat, config.gym_lon, weather_date, config.app_timezone)

        subtitle = (
            f"{workout.date} · preview available now"
            if slate.is_preview
            else f"{workout.date} · releases at {workout.release_time}"
        )
        tips_text = " · ".join(workout.technical_cues) if workout.technical_cues else ""
        tips_html = (
            f'<div style="margin-top:0.75rem;border-top:1px solid rgba(248,250,252,0.06);padding-top:0.6rem">'
            f'<div class="section-label" style="margin-bottom:0.2rem">Coach Tips</div>'
            f'<div style="color:#94a3b8;font-size:0.82rem">{tips_text}</div>'
            f'</div>'
        ) if tips_text else ""
        stimulus_html = (
            f'<div style="margin-top:0.75rem;border-top:1px solid rgba(248,250,252,0.06);padding-top:0.6rem">'
            f'<div class="section-label" style="margin-bottom:0.2rem">Stimulus</div>'
            f'<div style="color:#94a3b8;font-size:0.82rem">{workout.stimulus}</div>'
            f'</div>'
        ) if workout.stimulus else ""

        col_main = (
            f'<div class="hero-card">'
            f'<div class="eyebrow">Athlete View</div>'
            f'<div class="hero-title">{slate.heading}</div>'
            f'<div style="color:#94a3b8;font-size:0.85rem;margin-top:0.2rem">{subtitle}</div>'
            f'</div>'
            f'<div class="panel-card workout-block">'
            f'{format_workout_html(workout)}'
            f'{stimulus_html}'
            f'{tips_html}'
            f'</div>'
        )

        col_side = (
            _build_weather_html(weather)
            + f'<div class="panel-card" style="margin-top:0.75rem">'
            f'<div class="weather-section-label" style="margin-bottom:0.5rem">💬 Gym Conversation Starter</div>'
            f'{_build_hn_html(conversation_starter)}'
            f'</div>'
        )

        st.markdown(
            f'<div class="page-grid">'
            f'<div class="col-main">{col_main}</div>'
            f'<div class="col-side">{col_side}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    # Garage closed — single column.
    st.markdown(
        f'<div class="hero-card">'
        f'<div class="eyebrow">Athlete View</div>'
        f'<div class="garage-closed">{slate.heading}</div>'
        f'<div>{slate.message}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if slate.next_release_label:
        st.caption(f"Next scheduled release: {slate.next_release_label}")

    from datetime import date as _date
    today_iso = _date.today().isoformat()
    weather = _cached_fetch_weather(config.gym_lat, config.gym_lon, today_iso, config.app_timezone)
    st.markdown(
        _build_weather_html(weather)
        + f'<div class="panel-card" style="margin-top:0.75rem">'
        f'<div class="weather-section-label" style="margin-bottom:0.5rem">💬 Gym Conversation Starter</div>'
        f'{_build_hn_html(conversation_starter)}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _authenticate_admin(config: AppConfig) -> bool:
    st.sidebar.markdown("## Organizer")
    if not config.admin_enabled:
        st.sidebar.info("Set `ADMIN_PASSWORD` to unlock organizer tools.")
        return False

    if st.session_state.get("admin_authenticated"):
        st.sidebar.success("Organizer tools unlocked")
        if st.sidebar.button("Lock admin"):
            st.session_state["admin_authenticated"] = False
            st.rerun()
        return True

    password = st.sidebar.text_input("Admin password", type="password", key="admin_password_input")
    if st.sidebar.button("Unlock admin", use_container_width=True):
        if hmac.compare_digest(password, config.admin_password or ""):
            st.session_state["admin_authenticated"] = True
            st.rerun()
        st.sidebar.error("Incorrect password.")
    return False


def _render_record_list(records: list[WorkoutRecord], heading: str, query: str) -> None:
    st.subheader(heading)
    lowered_query = query.strip().lower()
    visible_records = []
    for record in sorted(records, key=lambda item: item.date, reverse=True):
        movement_names = " ".join(m.name for m in record.movements)
        searchable_text = " ".join(
            [record.date, record.release_time, record.workout_content, record.stimulus, " ".join(record.technical_cues), movement_names]
        ).lower()
        if not lowered_query or lowered_query in searchable_text:
            visible_records.append(record)

    if not visible_records:
        st.info("No workouts matched the current search.")
        return

    table_rows = []
    for record in visible_records:
        row: dict[str, str] = {
            "date": record.date,
            "release_time": record.release_time,
            "status": record.status,
            "stimulus": record.stimulus,
            "technical_cues": " | ".join(record.technical_cues),
            "content": format_workout_summary(record),
        }
        if record.movements:
            row["rx"] = " / ".join(m.rx_weight for m in record.movements if m.rx_weight) or "—"
            row["scaled"] = " / ".join(m.scaled_weight for m in record.movements if m.scaled_weight) or "—"
        table_rows.append(row)

    st.dataframe(table_rows, use_container_width=True, hide_index=True)


def _render_admin_console(
    config: AppConfig,
    records: list[WorkoutRecord],
    current_state: CurrentState,
    now_et: datetime,
    slate: AthleteSlate,
) -> None:
    st.write("")
    st.divider()
    st.header("Organizer Console")

    repository = _build_repository(config)
    if repository is None:
        st.error("GitHub repo settings are incomplete. Add the required secrets before staging workouts.")
        return

    total_workouts = len(records)
    upcoming_workouts = len([record for record in records if record.status != "archived"])
    col1, col2, col3 = st.columns(3)
    col1.metric("Stored workouts", total_workouts)
    col2.metric("Active records", upcoming_workouts)
    col3.metric("Current state", current_state.status.title())

    st.sidebar.markdown("### Time Check")
    st.sidebar.caption(f"Current App Time (ET): {now_et.strftime('%Y-%m-%d %I:%M:%S %p %Z')}")
    st.sidebar.caption(f"Logic Window Detected: {slate.logic_window}")

    search_query = st.text_input("Search history", placeholder="Date, benchmark, cue, or workout text")
    _render_record_list(records, "Workout History", search_query)

    st.subheader("Stage New Workout")
    with st.form("stage-workout"):
        workout_date = st.date_input("Workout date")
        release_time = st.time_input("Release time")
        workout_content = st.text_area(
            "Workout content",
            height=180,
            help="Free-text description or format header (e.g. '5 Rounds for Time'). Shown above the movement table when Movements JSON is provided.",
        )
        stimulus = st.text_area("Stimulus", height=90)
        technical_cues = st.text_area("Technical cues", height=120, help="One cue per line.")
        movements_json = st.text_area(
            "Movements (JSON — optional)",
            height=200,
            help=(
                "Structured movement list with Rx and Scaled weights. Leave blank for legacy text-only layout.\n\n"
                "Example:\n"
                '[{"name": "DB Snatches", "reps": "15", "rx_weight": "55 lbs", "scaled_weight": "35 lbs"},\n'
                ' {"name": "200m Run", "reps": "1"}]'
            ),
        )
        status = st.selectbox("Status", ["scheduled", "released", "archived"])
        submitted = st.form_submit_button("Stage New Workout", use_container_width=True)

    if submitted:
        import json as _json

        record_dict: dict = {
            "date": workout_date.isoformat(),
            "release_time": release_time.strftime("%H:%M"),
            "content": workout_content,
            "stimulus": stimulus,
            "technical_cues": technical_cues,
            "status": status,
        }
        if movements_json.strip():
            try:
                parsed_movements = _json.loads(movements_json.strip())
            except _json.JSONDecodeError as exc:
                st.error(f"Movements JSON is invalid: {exc}")
                parsed_movements = None
            if parsed_movements is not None:
                record_dict["movements"] = parsed_movements

        try:
            record = WorkoutRecord.from_dict(record_dict)
        except ValueError as exc:
            st.error(str(exc))
            record = None

        if record is not None:
            if record.movements:
                st.markdown('<div class="section-label">Workout Preview</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="panel-card workout-block">{format_workout_html(record)}</div>', unsafe_allow_html=True)
                st.write("")
            try:
                repository.stage_workout_and_open_state(record)
            except RuntimeError as exc:
                st.error(str(exc))
            else:
                st.success(f"Saved workout for {record.date} and reset the athlete slate to open.")


def _require_admin_write_access(config: AppConfig) -> None:
    if config.app_role != "admin":
        return
    has_write_token = bool(_secret_or_env("GITHUB_WRITE_TOKEN") or _secret_or_env("GITHUB_TOKEN"))
    if not has_write_token:
        st.error("Admin app is missing GITHUB_WRITE_TOKEN. Writes are disabled.")
        st.stop()


def main(app_role: AppRole = "athlete") -> None:
    st.set_page_config(
        page_title="TheAssembly",
        page_icon=":weight_lifter:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    config = _app_config(app_role)
    _require_admin_write_access(config)

    records, current_state, error_message = _load_data(config)
    now = datetime.now(pytz.timezone(config.app_timezone))
    slate = resolve_athlete_slate(records, current_state, now, config.app_timezone)
    _render_athlete_view(slate, config)

    if error_message:
        st.warning(error_message) if config.app_role == "admin" else st.caption("Organizer configuration is still in progress.")

    admin_enabled = _authenticate_admin(config) if config.app_role == "admin" else False
    if config.app_role == "admin" and admin_enabled:
        _render_admin_console(config, records, current_state, now, slate)


if __name__ == "__main__":
    # Default local behavior keeps current user-facing app as athlete portal.
    main(app_role="athlete")

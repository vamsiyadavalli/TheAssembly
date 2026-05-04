from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
import hmac
import os
import re
from uuid import uuid4

import pytz
import streamlit as st

from theassembly.github_repo import GitHubDataRepository, GitHubRepoConfig
from theassembly.hn_topics import HNConversationStarter, fetch_hn_conversation_starter
from theassembly.jokes import DailyJoke, fetch_daily_joke
from theassembly.models import CurrentState, PhotoRecord, WorkoutRecord, load_current_state, load_workouts
from theassembly.schedule import AthleteSlate, resolve_athlete_slate
from theassembly.weather import WorkoutWeather, fetch_workout_weather
from theassembly.analytics import fire_event, get_tracking_html
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
    .workout-caption {
        color: #fb923c;
        font-size: 0.9rem;
        font-style: italic;
        margin-bottom: 0.85rem;
        line-height: 1.45;
        border-left: 3px solid rgba(251, 146, 60, 0.4);
        padding-left: 0.65rem;
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
    .finisher-part-header {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        padding: 0.45rem 0 0.35rem 0;
        border-top: 1px solid rgba(245, 158, 11, 0.22);
        margin-bottom: 0.2rem;
    }
    .finisher-part-label {
        font-size: 0.7rem;
        font-weight: 700;
        color: #f59e0b;
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }
    .finisher-part-detail {
        font-size: 0.68rem;
        color: #94a3b8;
        font-style: italic;
    }
    .finisher-part-list {
        margin-bottom: 0.15rem;
    }
    /* ---- AI Poster: main-column click-to-expand ---- */
    .ai-poster-expand {
        display: block;
    }
    .ai-poster-expand > summary {
        cursor: pointer;
        list-style: none;
        position: relative;
        display: block;
    }
    .ai-poster-expand > summary::-webkit-details-marker { display: none; }
    .ai-poster-thumb {
        width: 100%;
        max-width: 760px;
        border-radius: 10px;
        display: block;
        opacity: 0.88;
        transition: opacity 0.18s;
    }
    .ai-poster-expand > summary:hover .ai-poster-thumb { opacity: 1; }
    .ai-poster-hint {
        position: absolute;
        bottom: 0.45rem;
        right: 0.45rem;
        background: rgba(2, 6, 23, 0.72);
        color: #94a3b8;
        font-size: 0.68rem;
        padding: 0.2rem 0.5rem;
        border-radius: 5px;
        letter-spacing: 0.05em;
        pointer-events: none;
    }
    .ai-poster-expand[open] > summary .ai-poster-hint { display: none; }
    .ai-poster-full {
        width: 100%;
        max-width: 760px;
        margin-top: 0.5rem;
        border-radius: 10px;
        display: block;
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
    /* ---- Photo slideshow ---- */
    .photo-slideshow {
        position: relative;
        overflow: hidden;
        border-radius: 10px;
        aspect-ratio: 4 / 3;
        background: rgba(15, 23, 42, 0.5);
    }
    .photo-slide {
        position: absolute;
        inset: 0;
        opacity: 0;
    }
    .photo-slide img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        border-radius: 10px;
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
    photos_folder_path: str


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
        photos_folder_path=_secret_or_env("PHOTOS_FOLDER_PATH", "photos") or "photos",
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
        photos_folder_path=config.photos_folder_path,
    )
    return GitHubDataRepository(repo_config)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_load_data(
    github_token: str,
    owner: str,
    repo: str,
    branch: str,
    workouts_file_path: str,
    current_state_file_path: str,
    photos_folder_path: str,
    gym_lat: float,
    gym_lon: float,
    app_timezone: str,
    app_role: str,
) -> tuple[list[WorkoutRecord], CurrentState, str | None]:
    _cfg = AppConfig(
        github_token=github_token or None,
        workouts_repo_owner=owner or None,
        workouts_repo_name=repo or None,
        workouts_repo_branch=branch,
        workouts_file_path=workouts_file_path,
        current_state_file_path=current_state_file_path,
        github_enabled=bool(github_token and owner and repo),
        app_timezone=app_timezone,
        admin_password=None,
        admin_enabled=False,
        gym_lat=gym_lat,
        gym_lon=gym_lon,
        photos_folder_path=photos_folder_path,
        app_role=app_role,
    )
    return _load_data(_cfg)


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


@st.cache_data(ttl=3600)
def _cached_fetch_daily_joke() -> DailyJoke | None:
    return fetch_daily_joke()


@st.cache_data(ttl=600)
def _cached_fetch_photos(
    target_date_iso: str,
    github_token: str,
    owner: str,
    repo: str,
    branch: str,
    photos_folder_path: str,
) -> list[PhotoRecord]:
    from datetime import date as _date
    from theassembly.github_repo import GitHubDataRepository, GitHubRepoConfig
    repo_config = GitHubRepoConfig(
        token=github_token,
        owner=owner,
        repo=repo,
        workouts_file_path="workouts.json",
        current_state_file_path="current_state.json",
        branch=branch,
        photos_folder_path=photos_folder_path,
    )
    repository = GitHubDataRepository(repo_config)
    return repository.fetch_photos(_date.fromisoformat(target_date_iso))


def _school_dress_hint(weather: WorkoutWeather) -> str:
    """Return a compact school-day outfit suggestion derived from morning conditions."""
    ref = next((h for h in weather.hours if h.hour == 6), None)
    if ref is None:
        ref = weather.hours[0] if weather.hours else None
    if ref is None:
        return ""
    feels = ref.feels_like
    if feels < 35:
        return "For school: heavy coat, hat & gloves — stays cold all day."
    if feels < 45:
        return "For school: insulated jacket, layer up underneath."
    if feels < 55:
        return "For school: light jacket or hoodie — might warm by lunch."
    if feels < 65:
        return "For school: hoodie works — you can tie it around your waist later."
    if feels < 75:
        return "For school: t-shirt and shorts should be just right."
    return "For school: light and breathable all day."


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

    school_dress = _school_dress_hint(weather)
    school_dress_html = (
        f'<div style="margin-top:0.75rem;border-top:1px solid rgba(248,250,252,0.06);padding-top:0.6rem">'
        f'<div class="weather-section-label" style="margin-bottom:0.3rem">👕 Dress for the Day</div>'
        f'<div style="font-size:0.82rem;color:#cbd5e1;line-height:1.5">🎒 {school_dress}</div>'
        f'</div>'
    ) if school_dress else ""

    return (
        f'<div class="panel-card">'
        f'<div class="weather-section-label">Dress for the Session · 5–8am</div>'
        f'<div class="weather-strip">{cards}</div>'
        f'<div class="clothing-rec">{weather.clothing_recommendation}</div>'
        f'{school_dress_html}'
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


def _build_joke_html(joke: DailyJoke | None) -> str:
    """Return HTML for the Joke of the Day card body."""
    from html import escape as _esc
    if joke is None:
        return '<span style="color:#94a3b8">No joke today — but you showed up. That\'s the punchline. 💪</span>'
    return (
        f'<div style="color:#e2e8f0;font-size:0.85rem;line-height:1.5;margin-bottom:0.55rem">'
        f'{_esc(joke.setup)}'
        f'</div>'
        f'<div style="color:#fb923c;font-size:0.85rem;font-weight:600;line-height:1.4">'
        f'{_esc(joke.delivery)}'
        f'</div>'
        f'<div style="margin-top:0.45rem;color:#64748b;font-size:0.75rem">'
        f'{_esc(joke.category)}'
        f'</div>'
    )


@st.cache_data(ttl=3600)
def _cached_fetch_ai_image_github(
    target_date_iso: str,
    github_token: str,
    owner: str,
    repo: str,
    branch: str,
    photos_folder_path: str,
) -> str | None:
    from datetime import date as _date
    from theassembly.github_repo import GitHubDataRepository, GitHubRepoConfig
    repo_config = GitHubRepoConfig(
        token=github_token,
        owner=owner,
        repo=repo,
        workouts_file_path="workouts.json",
        current_state_file_path="current_state.json",
        branch=branch,
        photos_folder_path=photos_folder_path,
    )
    repository = GitHubDataRepository(repo_config)
    return repository.fetch_ai_image(_date.fromisoformat(target_date_iso))


def _build_ai_image_html(workout_date_iso: str, config: "AppConfig") -> str:
    """Return HTML for the Movement Visualisation card, or '' if no image exists."""
    data_uri: str | None = None

    if config.github_enabled and config.github_token:
        data_uri = _cached_fetch_ai_image_github(
            workout_date_iso,
            config.github_token,
            config.workouts_repo_owner,
            config.workouts_repo_name,
            config.workouts_repo_branch,
            config.photos_folder_path,
        )
    else:
        # Local dev fallback: read from sibling TheAssemblyData repo.
        import base64 as _b64
        local_path = (
            Path(__file__).resolve().parent.parent
            / "TheAssemblyData"
            / "photos"
            / "ai"
            / f"{workout_date_iso}.png"
        )
        if local_path.exists():
            raw = local_path.read_bytes()
            data_uri = f"data:image/png;base64,{_b64.b64encode(raw).decode()}"

    if not data_uri:
        return ""

    return (
        f'<div class="panel-card" style="margin-top:0.75rem">'
        f'<div class="weather-section-label" style="margin-bottom:0.6rem">🏋️ Movement Visualisation</div>'
        f'<details class="ai-poster-expand">'
        f'<summary>'
        f'<img src="{data_uri}" class="ai-poster-thumb" alt="Workout poster preview">'
        f'<span class="ai-poster-hint">Tap to expand</span>'
        f'</summary>'
        f'<img src="{data_uri}" class="ai-poster-full" alt="AI-generated workout visualisation">'
        f'</details>'
        f'</div>'
    )


def _build_photos_html(photos: list[PhotoRecord]) -> tuple[str, str]:
    """Return (html, dynamic_css) for the post-workout photo gallery panel.

    Returns ("", "") when there are no photos so the panel is silently omitted.
    One photo: static image. Two or more: CSS-only crossfade slideshow.
    The dynamic_css must be injected via a separate st.markdown("<style>…</style>")
    call BEFORE the page-grid markdown, otherwise Streamlit strips <style> tags.
    """
    if not photos:
        return "", ""

    label = '<div class="weather-section-label" style="margin-bottom:0.6rem">📸 Post-Workout Shots</div>'

    if len(photos) == 1:
        img_html = (
            f'<img src="{photos[0].data_uri}" '
            f'style="width:100%;border-radius:10px;display:block" '
            f'alt="">'
        )
        return (
            f'<div class="panel-card" style="margin-top:0.75rem">'
            f'{label}'
            f'{img_html}'
            f'</div>'
        ), ""

    # Build per-photo keyframe rules: each photo is visible for 8 s, then fades out.
    n = len(photos)
    hold_pct = round(100 / n, 2)
    fade_pct = round(hold_pct + 5, 2)
    style_rules = ""
    for idx in range(n):
        delay = idx * 8
        style_rules += f".photo-slide:nth-child({idx + 1}){{animation-delay:{delay}s}}"
    keyframe = (
        f"@keyframes photo-fade{n}"
        f"{{0%{{opacity:1}}"
        f"{hold_pct}%{{opacity:1}}"
        f"{fade_pct}%{{opacity:0}}"
        f"100%{{opacity:0}}}}"
    )
    dynamic_css = keyframe + style_rules
    total_duration = n * 8

    slides_html = "".join(
        f'<div class="photo-slide" style="animation:{total_duration}s photo-fade{n} infinite">'
        f'<img src="{p.data_uri}" alt="">'
        f'</div>'
        for p in photos
    )

    return (
        f'<div class="panel-card" style="margin-top:0.75rem">'
        f'{label}'
        f'<div class="photo-slideshow">{slides_html}</div>'
        f'</div>'
    ), dynamic_css


def _generate_workout_caption(workout: WorkoutRecord, weather: WorkoutWeather | None) -> str:
    """Build a short friendly pre-workout caption from workout structure and weather."""
    content = workout.workout_content.lower()
    has_finisher = any(m.section.lower() == "finisher" for m in workout.movements)
    movement_count = len(workout.movements)

    weather_feel = ""
    if weather:
        ref = next((h for h in weather.hours if h.hour == 6), None)
        if ref:
            if ref.feels_like < 40:
                weather_feel = "cold"
            elif ref.feels_like > 75:
                weather_feel = "hot"

    if "partner" in content or "pair" in content or "team" in content:
        return "Partner in Pain — your partner is your pace car today. Lean on each other."
    if has_finisher:
        return "There's a finisher at the end. Pace yourself, then let it rip."
    if "amrap" in content:
        return "Every rep counts. Find your flow and keep the clock moving."
    if "for time" in content:
        return "Chase the clock — but pace the first round like you mean it."
    if movement_count >= 5:
        return "Long one today. Find a rhythm early and trust the process."
    if weather_feel == "cold":
        return "Cold outside — warm up well, your body will thank you mid-WOD."
    if weather_feel == "hot":
        return "It's warm out there. Pace yourself early — the heat is part of the workout."
    return "Show up, give your best, and leave it all on the floor."


def _render_athlete_view(slate: AthleteSlate, config: AppConfig) -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    _analytics_enabled = st.secrets.get("ANALYTICS_ENABLED", False)
    if _analytics_enabled:
        _tracking_html = get_tracking_html(
            ga4_id=st.secrets.get("GA4_MEASUREMENT_ID", ""),
            clarity_id=st.secrets.get("CLARITY_PROJECT_ID", ""),
            app_role=config.app_role,
            gym_status=slate.status,
        )
        if _tracking_html:
            # st.html sanitizes/embeds HTML without executing tracking JS.
            # Use an iframe component so GA4/Clarity scripts can run.
            st.components.v1.html(_tracking_html, height=0)

    _ga4_id, _ga4_secret = _analytics_cfg()
    _client_id = _analytics_client_id(config)
    if not st.session_state.get("_evt_page_view_fired"):
        fire_event(
            _ga4_id,
            _ga4_secret,
            "page_view",
            {
                **_analytics_event_context(config),
                "engagement_time_msec": 1000,
            },
            client_id=_client_id,
        )
        st.session_state["_evt_page_view_fired"] = True

    st.title("TheAssembly")

    # Pre-fetch both async data sources before building HTML.
    conversation_starter = _cached_fetch_hn_conversation_starter()

    def _fetch_photos_for_date(date_iso: str) -> list[PhotoRecord]:
        if not config.github_enabled or not config.github_token:
            return []
        return _cached_fetch_photos(
            date_iso,
            config.github_token,
            config.workouts_repo_owner,
            config.workouts_repo_name,
            config.workouts_repo_branch,
            config.photos_folder_path,
        )

    if slate.status == "open" and slate.workout is not None:
        workout = slate.workout
        from datetime import date as _date_today
        weather_date = workout.workout_date.isoformat()
        weather = _cached_fetch_weather(config.gym_lat, config.gym_lon, weather_date, config.app_timezone)
        joke = _cached_fetch_daily_joke()
        photos = _fetch_photos_for_date(_date_today.today().isoformat())

        # ── GA4: workout_viewed / workout_preview_viewed ──────────────────────
        if slate.is_preview:
            _evt_key = f"_evt_preview_viewed_{workout.date}"
            if not st.session_state.get(_evt_key):
                fire_event(
                    _ga4_id,
                    _ga4_secret,
                    "workout_preview_viewed",
                    _analytics_event_context(config, workout.date),
                    client_id=_client_id,
                )
                st.session_state[_evt_key] = True
        else:
            _evt_key = f"_evt_workout_viewed_{workout.date}"
            if not st.session_state.get(_evt_key):
                fire_event(
                    _ga4_id,
                    _ga4_secret,
                    "workout_viewed",
                    _analytics_event_context(config, workout.date),
                    client_id=_client_id,
                )
                st.session_state[_evt_key] = True

        subtitle = (
            f"{workout.date} · preview available now"
            if slate.is_preview
            else f"{workout.date} · releases at {workout.release_time}"
        )
        from html import escape as _esc
        caption_text = workout.caption if workout.caption else _generate_workout_caption(workout, weather)
        caption_html = f'<div class="workout-caption">{_esc(caption_text)}</div>' if caption_text else ""
        tips_lines = "".join(
            f'<div style="margin-bottom:0.25rem">{cue}</div>'
            for cue in workout.technical_cues
        ) if workout.technical_cues else ""
        tips_html = (
            f'<div style="margin-top:0.75rem;border-top:1px solid rgba(248,250,252,0.06);padding-top:0.6rem">'
            f'<div class="section-label" style="margin-bottom:0.35rem">Coach Tips</div>'
            f'<div style="color:#e2e8f0;font-size:0.82rem;line-height:1.5">{tips_lines}</div>'
            f'</div>'
        ) if tips_lines else ""
        stimulus_html = (
            f'<div style="margin-top:0.75rem;border-top:1px solid rgba(248,250,252,0.06);padding-top:0.6rem">'
            f'<div class="section-label" style="margin-bottom:0.2rem">Stimulus</div>'
            f'<div style="color:#e2e8f0;font-size:0.82rem">{workout.stimulus}</div>'
            f'</div>'
        ) if workout.stimulus else ""

        col_side_photos_html, col_side_photos_css = _build_photos_html(photos)
        col_side_ai_image_html = _build_ai_image_html(workout.workout_date.isoformat(), config)
        col_main = (
            f'<div class="hero-card">'
            f'<div class="eyebrow">Athlete View</div>'
            f'<div class="hero-title">{slate.heading}</div>'
            f'<div style="color:#94a3b8;font-size:0.85rem;margin-top:0.2rem">{subtitle}</div>'
            f'</div>'
            f'<div class="panel-card workout-block">'
            f'{caption_html}'
            f'{format_workout_html(workout)}'
            f'{stimulus_html}'
            f'{tips_html}'
            f'</div>'
            + col_side_ai_image_html
        )

        col_side = (
            _build_weather_html(weather)
            + f'<div class="panel-card" style="margin-top:0.75rem">'
            f'<div class="weather-section-label" style="margin-bottom:0.5rem">😄 Joke of the Day</div>'
            f'{_build_joke_html(joke)}'
            f'</div>'
            + col_side_photos_html
            + f'<div class="panel-card" style="margin-top:0.75rem">'
            f'<div class="weather-section-label" style="margin-bottom:0.5rem">💬 Gym Conversation Starter</div>'
            f'{_build_hn_html(conversation_starter)}'
            f'</div>'
        )

        if col_side_photos_css:
            st.markdown(f"<style>{col_side_photos_css}</style>", unsafe_allow_html=True)
        st.markdown(
            f'<div class="page-grid">'
            f'<div class="col-main">{col_main}</div>'
            f'<div class="col-side">{col_side}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    # ── GA4: garage_closed_view ───────────────────────────────────────────────
    from datetime import date as _date
    today_iso = _date.today().isoformat()
    _evt_key_closed = f"_evt_garage_closed_{today_iso}"
    if not st.session_state.get(_evt_key_closed):
        fire_event(
            _ga4_id,
            _ga4_secret,
            "garage_closed_view",
            {
                **_analytics_event_context(config),
                "date": today_iso,
            },
            client_id=_client_id,
        )
        st.session_state[_evt_key_closed] = True

    # Garage closed — use the same 2-col grid to eliminate desktop whitespace.
    weather = _cached_fetch_weather(config.gym_lat, config.gym_lon, today_iso, config.app_timezone)
    joke = _cached_fetch_daily_joke()
    photos = _fetch_photos_for_date(today_iso)

    next_release_html = (
        f'<div style="margin-top:0.5rem;color:#64748b;font-size:0.8rem">'
        f'Next scheduled release: {slate.next_release_label}'
        f'</div>'
    ) if slate.next_release_label else ""

    closed_main = (
        f'<div class="hero-card">'
        f'<div class="eyebrow">Athlete View</div>'
        f'<div class="garage-closed">{slate.heading}</div>'
        f'<div>{slate.message}</div>'
        f'{next_release_html}'
        f'</div>'
    )

    closed_photos_html, closed_photos_css = _build_photos_html(photos)
    closed_side = (
        _build_weather_html(weather)
        + f'<div class="panel-card" style="margin-top:0.75rem">'
        f'<div class="weather-section-label" style="margin-bottom:0.5rem">😄 Joke of the Day</div>'
        f'{_build_joke_html(joke)}'
        f'</div>'
        + closed_photos_html
        + f'<div class="panel-card" style="margin-top:0.75rem">'
        f'<div class="weather-section-label" style="margin-bottom:0.5rem">💬 Gym Conversation Starter</div>'
        f'{_build_hn_html(conversation_starter)}'
        f'</div>'
    )

    if closed_photos_css:
        st.markdown(f"<style>{closed_photos_css}</style>", unsafe_allow_html=True)
    st.markdown(
        f'<div class="page-grid">'
        f'<div class="col-main">{closed_main}</div>'
        f'<div class="col-side">{closed_side}</div>'
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
    if st.sidebar.button("Unlock admin", width='stretch'):
        if hmac.compare_digest(password, config.admin_password or ""):
            st.session_state["admin_authenticated"] = True
            _ga4_id, _ga4_secret = _analytics_cfg()
            _client_id = _analytics_client_id(config)
            if not st.session_state.get("_evt_admin_authenticated_fired"):
                fire_event(
                    _ga4_id,
                    _ga4_secret,
                    "admin_authenticated",
                    _analytics_event_context(config),
                    client_id=_client_id,
                )
                st.session_state["_evt_admin_authenticated_fired"] = True
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

    st.dataframe(table_rows, width='stretch', hide_index=True)


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
        submitted = st.form_submit_button("Stage New Workout", width='stretch')

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
                _ga4_id, _ga4_secret = _analytics_cfg()
                _client_id = _analytics_client_id(config)
                _submit_sig = f"{record.date}|{record.release_time}|{record.status}|{len(record.movements)}"
                _last_sig = str(st.session_state.get("_evt_last_publish_signature", ""))
                if _submit_sig != _last_sig:
                    fire_event(
                        _ga4_id,
                        _ga4_secret,
                        "gym_workout_publish",
                        _analytics_event_context(config, record.date),
                        client_id=_client_id,
                    )
                    fire_event(
                        _ga4_id,
                        _ga4_secret,
                        "gym_admin_toggle_status",
                        {
                            **_analytics_event_context(config, record.date),
                            "new_status": "open",
                        },
                        client_id=_client_id,
                    )
                    st.session_state["_evt_last_publish_signature"] = _submit_sig
                st.success(f"Saved workout for {record.date} and reset the athlete slate to open.")
                _cached_load_data.clear()

    # ---- Upload Workout Photos ----
    st.subheader("Upload Workout Photos")
    st.caption(
        f"Photos are stored in `{config.photos_folder_path}/` in the data repo. "
        "Name format after upload: `YYYY-MM-DD-<original_filename>`. "
        "Supports JPG and PNG, max 6 photos per day shown on the portal."
    )
    from datetime import date as _today_date
    photo_date = st.date_input("Photo date", value=_today_date.today(), key="photo_upload_date")
    uploaded_files = st.file_uploader(
        "Select photos",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key="photo_upload_files",
    )
    if st.button("Upload Photos", disabled=not uploaded_files, width='stretch'):
        success_count = 0
        for uploaded_file in uploaded_files:
            try:
                repository.upload_photo(
                    photo_date.isoformat(),
                    uploaded_file.name,
                    uploaded_file.read(),
                )
                st.success(f"✅ Uploaded `{uploaded_file.name}`")
                success_count += 1
            except RuntimeError as exc:
                st.error(f"❌ Failed to upload `{uploaded_file.name}`: {exc}")
        if success_count:
            _cached_fetch_photos.clear()
            st.info("Photo cache cleared — the gallery will show the new photos on next load.")


def _require_admin_write_access(config: AppConfig) -> None:
    if config.app_role != "admin":
        return
    has_write_token = bool(_secret_or_env("GITHUB_WRITE_TOKEN") or _secret_or_env("GITHUB_TOKEN"))
    if not has_write_token:
        st.error("Admin app is missing GITHUB_WRITE_TOKEN. Writes are disabled.")
        st.stop()


def _analytics_cfg() -> tuple[str, str]:
    """Return (ga4_measurement_id, ga4_mp_api_secret) when analytics is enabled, else ('', '')."""
    if not st.secrets.get("ANALYTICS_ENABLED", False):
        return "", ""
    return (
        str(st.secrets.get("GA4_MEASUREMENT_ID", "") or ""),
        str(st.secrets.get("GA4_MP_API_SECRET", "") or ""),
    )


def _analytics_client_id(config: AppConfig) -> str:
    """Return a stable GA4 client_id for the current Streamlit session."""
    key = f"_ga_client_id_{config.app_role}"
    current = st.session_state.get(key)
    if not current:
        current = f"{config.app_role}-{uuid4()}"
        st.session_state[key] = current
    return str(current)


def _analytics_event_context(config: AppConfig, workout_date: str | None = None) -> dict[str, str]:
    """Shared event context for GA4 Measurement Protocol events."""
    params: dict[str, str] = {
        "app_role": config.app_role,
        "page_location": "https://asm-athlete.streamlit.app/" if config.app_role == "athlete" else "https://asm-control.streamlit.app/",
    }
    if workout_date:
        params["workout_date"] = workout_date
    return params



def main(app_role: AppRole = "athlete") -> None:
    st.set_page_config(
        page_title="TheAssembly",
        page_icon=":weight_lifter:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    config = _app_config(app_role)
    _require_admin_write_access(config)

    records, current_state, error_message = _cached_load_data(
        github_token=config.github_token or "",
        owner=config.workouts_repo_owner or "",
        repo=config.workouts_repo_name or "",
        branch=config.workouts_repo_branch,
        workouts_file_path=config.workouts_file_path,
        current_state_file_path=config.current_state_file_path,
        photos_folder_path=config.photos_folder_path,
        gym_lat=config.gym_lat,
        gym_lon=config.gym_lon,
        app_timezone=config.app_timezone,
        app_role=config.app_role,
    )
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

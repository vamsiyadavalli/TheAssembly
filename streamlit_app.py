from __future__ import annotations

from datetime import datetime
import hmac
from pathlib import Path

import pytz
import streamlit as st

from theassembly.config import load_config
from theassembly.github_repo import GitHubDataRepository, GitHubRepoConfig
from theassembly.models import CurrentState, WorkoutRecord, load_current_state, load_workouts
from theassembly.schedule import APP_TIMEZONE_NAME, AthleteSlate, resolve_athlete_slate


st.set_page_config(
    page_title="TheAssembly",
    page_icon=":weight_lifter:",
    layout="centered",
    initial_sidebar_state="collapsed",
)


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
</style>
"""


def _app_config():
    try:
        secrets = dict(st.secrets)
    except Exception:
        secrets = {}
    return load_config(secrets)


def _build_repository(config) -> GitHubDataRepository | None:
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


def _load_data(config) -> tuple[list[WorkoutRecord], CurrentState, str | None]:
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
        return [], CurrentState(status="closed"), str(exc)

    return records, current_state, None


def _render_athlete_view(slate: AthleteSlate) -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.title("TheAssembly")

    if slate.status == "open" and slate.workout is not None:
        workout = slate.workout
        subtitle = (
            f"{workout.date} - preview available now"
            if slate.is_preview
            else f"{workout.date} - releases at {workout.release_time}"
        )
        st.markdown(
            f"""
            <div class="hero-card">
                <div class="eyebrow">Athlete View</div>
                <div class="hero-title">{slate.heading}</div>
                <div>{subtitle}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.write("")
        st.markdown('<div class="section-label">Workout Content</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="panel-card workout-block">{workout.workout_content}</div>', unsafe_allow_html=True)
        st.write("")
        st.markdown('<div class="section-label">Stimulus</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="panel-card">{workout.stimulus}</div>', unsafe_allow_html=True)
        st.write("")
        st.markdown('<div class="section-label">Technical Cues</div>', unsafe_allow_html=True)
        cue_markup = "".join(f'<span class="cue-chip">{cue}</span>' for cue in workout.technical_cues)
        st.markdown(f'<div class="panel-card">{cue_markup}</div>', unsafe_allow_html=True)
        return

    st.markdown(
        f"""
        <div class="hero-card">
            <div class="eyebrow">Athlete View</div>
            <div class="garage-closed">{slate.heading}</div>
            <div>{slate.message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if slate.next_release_label:
        st.caption(f"Next scheduled release: {slate.next_release_label}")


def _authenticate_admin(config) -> bool:
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
        searchable_text = " ".join(
            [record.date, record.release_time, record.workout_content, record.stimulus, " ".join(record.technical_cues)]
        ).lower()
        if not lowered_query or lowered_query in searchable_text:
            visible_records.append(record)

    if not visible_records:
        st.info("No workouts matched the current search.")
        return

    table_rows = []
    for record in visible_records:
        table_rows.append(
            {
                "date": record.date,
                "release_time": record.release_time,
                "status": record.status,
                "stimulus": record.stimulus,
                "technical_cues": " | ".join(record.technical_cues),
                "content": record.workout_content,
            }
        )

    st.dataframe(table_rows, use_container_width=True, hide_index=True)


def _render_admin_console(
    config,
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
        workout_content = st.text_area("Workout content", height=180)
        stimulus = st.text_area("Stimulus", height=90)
        technical_cues = st.text_area("Technical cues", height=120, help="One cue per line.")
        status = st.selectbox("Status", ["scheduled", "released", "archived"])
        submitted = st.form_submit_button("Stage New Workout", use_container_width=True)

    if submitted:
        record = WorkoutRecord.from_dict(
            {
                "date": workout_date.isoformat(),
                "release_time": release_time.strftime("%H:%M"),
                "content": workout_content,
                "stimulus": stimulus,
                "technical_cues": technical_cues,
                "status": status,
            }
        )
        try:
            repository.stage_workout_and_open_state(record)
        except RuntimeError as exc:
            st.error(str(exc))
        else:
            st.success(f"Saved workout for {record.date} and reset the athlete slate to open.")


def main() -> None:
    config = _app_config()
    admin_enabled = _authenticate_admin(config)
    records, current_state, error_message = _load_data(config)
    now = datetime.now(pytz.timezone(APP_TIMEZONE_NAME))

    # Debug: Show bridge/config status and fetch errors.
    st.info(
        "[DEBUG] Bridge config: "
        f"github_enabled={config.github_enabled}, "
        f"owner={config.workouts_repo_owner or '(missing)'}, "
        f"repo={config.workouts_repo_name or '(missing)'}, "
        f"branch={config.workouts_repo_branch}, "
        f"workouts_path={config.workouts_file_path}, "
        f"state_path={config.current_state_file_path}, "
        f"timezone={config.timezone_name}"
    )
    if error_message:
        st.error(f"[DEBUG] Data bridge error: {error_message}")

    # Debug: Show loaded workout records
    debug_records = []
    for r in records:
        debug_records.append({
            'date': getattr(r, 'date', None),
            'workout_date': getattr(r, 'workout_date', None),
            'release_time': getattr(r, 'release_time', None),
            'status': getattr(r, 'status', None),
            'keys': list(r.__dict__.keys()) if hasattr(r, '__dict__') else str(type(r))
        })
    st.info(f"[DEBUG] Loaded records: {debug_records}")

    # Debug: Show current time, logic window, and target date
    from theassembly.schedule import detect_logic_window
    logic_window, target_date, is_preview = detect_logic_window(now)
    st.info(f"[DEBUG] Now (ET): {now.strftime('%Y-%m-%d %I:%M:%S %p %Z')}, Logic window: {logic_window}, Target date: {target_date}, Is preview: {is_preview}")

    slate = resolve_athlete_slate(records, current_state, now, config.timezone_name)
    _render_athlete_view(slate)

    if error_message:
        if admin_enabled:
            st.warning(error_message)
        else:
            st.caption("Organizer configuration is still in progress.")

    if admin_enabled:
        _render_admin_console(config, records, current_state, now, slate)


if __name__ == "__main__":
    main()

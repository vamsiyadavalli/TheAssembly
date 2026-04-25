# Contributing to TheAssembly

Thanks for your interest in contributing! This guide is for developers who want to run, modify, or extend the codebase.

## Architecture overview

> [View architecture diagram →](docs/architecture.mmd)

TheAssembly is a two-repo system:

- **TheAssembly** (this repo) — the Streamlit app. Contains all code, zero workout data.
- **Your data repo** (e.g. `YourGymName-data`) — private GitHub repo containing `workouts.json` and `current_state.json`. Never shared.

## Local development

### Prerequisites

- Python 3.11+, or Docker

### Option A — Python directly

```bash
# Install dependencies
pip install -r requirements.txt

# Copy secrets template
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Fill in your tokens and repo settings

# Run athlete app (terminal 1)
python -m streamlit run athlete_app.py

# Run admin app (terminal 2)
python -m streamlit run admin_app.py
```

### Option B — Docker Compose (both apps at once)

```bash
# Copy secrets template
cp docker-compose.override.env.example docker-compose.override.env
# Fill in your tokens and repo settings

# Start both apps
docker compose up

# Athlete app → http://localhost:8501
# Admin app   → http://localhost:8502
```

### Option C — VS Code Dev Container / GitHub Codespaces

Open the repo in VS Code and choose **Reopen in Container** when prompted. The devcontainer builds from `Dockerfile` and starts the athlete app automatically.

## Running tests

```bash
PYTHONPATH=. pytest tests/ -q
```

CI runs on push/PR to `dev` and `master` via `.github/workflows/tests.yml`.

## Code structure

| File/Module | Purpose |
|---|---|
| `streamlit_app.py` | All rendering + admin logic; `main(app_role)` is the entry point |
| `athlete_app.py` | Thin wrapper: calls `main(app_role="athlete")` |
| `admin_app.py` | Thin wrapper: calls `main(app_role="admin")` |
| `theassembly/config.py` | `AppConfig` + `load_config()` — reads secrets/env vars |
| `theassembly/models.py` | `WorkoutRecord`, `CurrentState`, serialization/deserialization |
| `theassembly/github_repo.py` | `GitHubDataRepository` — all GitHub API I/O |
| `theassembly/schedule.py` | `resolve_athlete_slate()` + time-window logic |

## Branch strategy

- `feature/*` → `dev` (integration)
- `dev` → `master` (production, Streamlit Cloud deployment source)
- Squash merges preferred to keep history clean

## Secrets — local only

`.streamlit/secrets.toml` and `docker-compose.override.env` are both in `.gitignore`. Never commit live tokens.

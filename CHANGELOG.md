# Changelog

All notable changes to TheAssembly are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Added
- `LICENSE` — MIT license for the app code (workout data in your private data repo is unaffected)
- `Dockerfile` — single image for both app roles; role selected via command override
- `docker-compose.yml` — runs athlete app (port 8501) and admin app (port 8502) together with one command
- `docker-compose.override.env.example` — secrets template for Docker local development
- `SETUP.md` — step-by-step gym owner deployment guide (no coding required)
- `CONTRIBUTING.md` — developer setup, code structure, and branch strategy
- `gym-config-checklist.md` — fillable checklist for configuring a new gym deployment
- `docs/architecture.mmd` — Mermaid architecture diagram (separate `.mmd` file, linked from README)
- `CHANGELOG.md` — this file

### Changed
- `.devcontainer/devcontainer.json` — now builds from `Dockerfile` instead of a generic Python image
- `.gitignore` — added `docker-compose.override.env` to prevent accidental secret commits
- `README.md` — restructured for two audiences: gym owners and developers

---

## [0.1.0] — Initial release

### Added
- Athlete whiteboard view with time-gated workout display (overnight + preview windows)
- Organizer console with workout staging, search, and state control
- GitHub-backed data layer (`workouts.json` + `current_state.json` via GitHub Contents API)
- Split token support: `GITHUB_READ_TOKEN` (athlete) + `GITHUB_WRITE_TOKEN` (admin)
- Self-wipe "Garage Closed" state from 9:01 AM – 3:59 PM ET
- Preview window: tomorrow's workout visible from 4:00 PM – 11:59 PM ET
- Workout monitoring GitHub Actions workflow
- Memory profiling tooling (`tools/memory_profile_streamlit.sh`)

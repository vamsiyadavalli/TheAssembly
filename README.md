# TheAssembly

TheAssembly is a privacy-first fitness whiteboard built for Streamlit Community Cloud.

## Architecture

> [View architecture diagram →](docs/architecture.mmd)

## What it does
- **Athlete view:** shows only the current workout window - tomorrow during the 4:00 PM preview or today during the overnight session.
- **Self-wipe:** shows a high-contrast `Garage Closed` state from 9:01 AM through 11:59 AM in `America/New_York`.
- **Organizer view:** unlocks from the sidebar with a shared admin password and can search history or stage future workouts.
- **Secret bridge:** reads `workouts.json` and `current_state.json` from the private `TheAssemblyData` GitHub repository using `requests` plus a GitHub Personal Access Token.

## Required secrets

Set these in Streamlit Community Cloud or as environment variables:

| Key | Required | Purpose |
| --- | --- | --- |
| `GITHUB_WRITE_TOKEN` | No | **Admin app:** GitHub PAT with Contents: Read & Write for TheAssemblyData. Used for write operations. |
| `GITHUB_READ_TOKEN` | No | **Athlete app:** GitHub PAT with Contents: Read-only for TheAssemblyData. Used for read-only access. |
| `GITHUB_TOKEN` | Yes | Fallback PAT if role-specific tokens are not set. Must have at least Contents: Read & Write for admin, Read-only for athlete. |
| `WORKOUTS_REPO_OWNER` | Yes | Repo owner for the private workouts repo |
| `WORKOUTS_REPO_NAME` | Yes | Repo name for the private workouts repo, typically `TheAssemblyData` |
| `WORKOUTS_FILE_PATH` | No | Path to the JSON file, defaults to `workouts.json` |
| `CURRENT_STATE_FILE_PATH` | No | Path to the state file, defaults to `current_state.json` |
| `WORKOUTS_REPO_BRANCH` | No | Branch name, defaults to `main` (set to your actual data repo branch, e.g. `master`) |
| `ADMIN_PASSWORD` | Yes | Shared password for the organizer sidebar |
| `APP_TIMEZONE` | No | Defaults to `America/New_York` |

**Token selection logic:**
- Admin app uses `GITHUB_WRITE_TOKEN` if set, else falls back to `GITHUB_TOKEN`.
- Athlete app uses `GITHUB_READ_TOKEN` if set, else falls back to `GITHUB_TOKEN`.

**Token format:**
- Paste only the raw token value (e.g., `github_pat_...` or `ghp_...`). Do not include labels or extra text.

**PAT permissions:**
- Fine-grained PAT: grant repository access to TheAssemblyData with Contents: Read & Write (admin) or Read-only (athlete).
- Classic PAT: grant `repo` scope for private repo access.

### Local setup (step-by-step)
1. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.
2. Fill in either split tokens (`GITHUB_READ_TOKEN` + `GITHUB_WRITE_TOKEN`) or a single fallback `GITHUB_TOKEN`, plus repo settings.
3. Restart Streamlit.


Example for split deployment:

```toml
# For athlete app (read-only)
GITHUB_READ_TOKEN = "github_pat_xxx"
WORKOUTS_REPO_OWNER = "your-github-owner"
WORKOUTS_REPO_NAME = "TheAssemblyData"
WORKOUTS_FILE_PATH = "workouts.json"
CURRENT_STATE_FILE_PATH = "current_state.json"
WORKOUTS_REPO_BRANCH = "master"
APP_TIMEZONE = "America/New_York"

# For admin app (read/write)
GITHUB_WRITE_TOKEN = "github_pat_xxx"
WORKOUTS_REPO_OWNER = "your-github-owner"
WORKOUTS_REPO_NAME = "TheAssemblyData"
WORKOUTS_FILE_PATH = "workouts.json"
CURRENT_STATE_FILE_PATH = "current_state.json"
WORKOUTS_REPO_BRANCH = "master"
APP_TIMEZONE = "America/New_York"
ADMIN_PASSWORD = "your-admin-password"
```

`.streamlit/secrets.toml` is ignored by git via `.gitignore`.


### Verify bridge is active (step 3)
After restart, the debug lines in the app should show:
- `github_enabled=True`
- `owner` and `repo` populated
- no `Data bridge error`
- `Loaded records` contains workout entries

If you still see `github_enabled=False`, your secrets are not being picked up in the current runtime.

### Troubleshooting

- **401 Bad credentials:**
  - Check that your token is valid, not expired, and pasted with no extra text or labels.
  - For admin, ensure `GITHUB_WRITE_TOKEN` is set and has Contents: Read & Write for TheAssemblyData.
  - For athlete, ensure `GITHUB_READ_TOKEN` is set and has Contents: Read-only for TheAssemblyData.
  - If using `GITHUB_TOKEN`, ensure it has the correct permissions for the app role.

- **404 Not Found:**
  - Check that `WORKOUTS_REPO_OWNER`, `WORKOUTS_REPO_NAME`, `WORKOUTS_FILE_PATH`, `CURRENT_STATE_FILE_PATH`, and `WORKOUTS_REPO_BRANCH` match your repo exactly.
  - Ensure your PAT has access to the repo and the files exist at the specified paths.
  - A PAT without repo access can also surface as 404.

## JSON shape
`workouts.json` should contain an array of records:

```json
[
  {
    "date": "2026-04-20",
    "release_time": "05:30",
    "content": "5 rounds for time: 400m run, 15 wall balls, 10 burpees",
    "stimulus": "Moderate aerobic repeatability with clean pacing.",
    "technical_cues": [
      "Relax shoulders on the run.",
      "Break wall balls before form slips."
    ],
    "status": "scheduled"
  }
]
```

The canonical schema uses `content`. The loader also accepts legacy `workout_content` plus title-cased keys like `Date`, `Release Time`, and `Workout Content`.

## State gating
`current_state.json` should contain:

```json
{
  "status": "open"
}
```

Athletes only see today's workout when:
- the current app time in `America/New_York` is between `12:00 AM` and `9:00 AM`
- `current_state.json` is `open`

Athletes can preview tomorrow's workout when:
- the current local time in `America/New_York` is between `12:00 PM` and `11:59 PM`
- `current_state.json` is `open`

From `9:01 AM` through `11:59 AM`, the athlete view always shows **Garage Closed**.

Organizer staging saves the new workout and resets `current_state.json` back to `open`.

## Run locally
```bash
streamlit run streamlit_app.py
```

### Quickstart commands
```bash
cd /usr/local/git/TheAssembly

# Install dependencies
python3 -m pip install -r requirements.txt

# Create local secrets file from template (one-time setup)
cp .streamlit/secrets.toml.example .streamlit/secrets.toml

# Run athlete app (terminal 1)
python3 -m streamlit run athlete_app.py

# Run admin app (terminal 2)
python3 -m streamlit run admin_app.py

# Run tests
PYTHONPATH=. pytest tests/test_schedule.py -q
```

Run athlete and admin in separate terminals so each process can own its Streamlit port.

In VS Code you can launch both at once: open the Command Palette, choose **Tasks: Run Task**, and select **Run Both Apps (Athlete + Admin)**. Each app opens in its own dedicated terminal panel.

## Test locally
```bash
python3 -m unittest discover -s tests
```

## Branch Strategy and CI

Recommended lightweight flow:
1. `feature/*` branches target `dev`.
2. `dev` is your integration branch.
3. `master` is production and Streamlit deployment source.

CI workflow:
- `.github/workflows/tests.yml` runs on push and pull requests for `dev` and `master`.
- It runs unit tests and a non-blocking Ruff lint step.

Monitoring workflow:
- `.github/workflows/workout-monitoring.yml` runs on cron and manual dispatch.
- It validates data in `TheAssemblyData`, checks for missing workouts, and emits warning/critical status.
- Alerts are handled via GitHub Actions run status, step summary output, and native GitHub failure emails.
- Legacy `.github/workflows/daily-workout-status.yml` was retired to avoid duplicate scheduled checks.

Suggested repository protection rules:
1. Require pull requests to merge into `master`.
2. Require CI checks to pass before merge.
3. Prefer squash merges to keep history clean.

## Post-Launch Operations

### Daily smoke test (2-3 minutes)
1. Open athlete app URL.
2. Confirm app loads and shows expected slate state for current ET window.
3. Open admin app URL and unlock organizer tools.
4. Confirm Organizer Console appears.
5. Stage a small test workout only when you intend to validate write flow.

### Weekly maintenance
1. Confirm both app secrets are still present in Streamlit Cloud.
2. Verify `WORKOUTS_REPO_BRANCH`, owner, repo, and file paths still match `TheAssemblyData`.
3. Check recent commits in `TheAssemblyData` for expected updates only.

### Incident response quick guide

- `401 Bad credentials`
  - Re-check token format in Streamlit secrets (raw token only).
  - Verify PAT has not expired/revoked.
  - Confirm admin uses write token and athlete uses read token.

- `404 Not Found`
  - Verify `WORKOUTS_REPO_OWNER`, `WORKOUTS_REPO_NAME`, `WORKOUTS_REPO_BRANCH`, and file paths.
  - Verify PAT has repository access to `TheAssemblyData`.

- Athlete shows `Garage Closed` unexpectedly
  - Confirm app local time is ET and current window is open or preview.
  - Verify `current_state.json` status is `open`.
  - Verify a workout exists for the expected target date.

### Security hygiene
1. Rotate `GITHUB_READ_TOKEN` and `GITHUB_WRITE_TOKEN` on a regular cadence.
2. Rotate `ADMIN_PASSWORD` periodically.
3. Never commit live secrets into git.

### Monitoring secrets
Configure these repository secrets for `.github/workflows/workout-monitoring.yml`:

Minimal setup (no Slack, no SMTP):
- Use `.github/monitoring-secrets.env.example` as your copy/paste template.
- Add only those keys in GitHub repository secrets.
- Skip `SLACK_WEBHOOK_URL` and all `MAIL_*` secrets if you only want GitHub Actions summaries + native GitHub failure emails.

- Required:
  - `MONITOR_GITHUB_TOKEN` (PAT with read access to `TheAssemblyData`)
  - `WORKOUTS_REPO_OWNER`
  - `WORKOUTS_REPO_NAME`
- Optional overrides:
  - `WORKOUTS_REPO_BRANCH` (defaults to `master`)
  - `WORKOUTS_FILE_PATH` (defaults to `workouts.json`)
  - `CURRENT_STATE_FILE_PATH` (defaults to `current_state.json`)
  - `APP_TIMEZONE` (defaults to `America/New_York`)

### Release checklist
1. Update data in `TheAssemblyData` and commit.
2. Validate JSON shape (`workouts.json`, `current_state.json`).
3. Confirm athlete/admin behavior on deployed URLs after push.
4. If needed, use Streamlit reboot to force fresh secret/config load.

## Memory Capacity Profiling

Streamlit Community Cloud allows **1 GB** of memory per app deployment. Use the script below to measure local process RSS across athlete scenarios and the admin idle baseline, then estimate cloud headroom.

> **Scope note:** Admin interaction-peak profiling is intentionally excluded. The admin app is coordinator-only, so only its idle baseline is measured.

### Prerequisites
1. Both apps running locally (see [Quickstart commands](#quickstart-commands)).
2. Note the PID of each process (see step 1 below).

### How to run

**Step 1 — capture PIDs after starting apps:**
```bash
# In a separate terminal after both apps are running:
pgrep -af streamlit
# Note the PID of athlete_app.py (PID_A) and admin_app.py (PID_ADM)
```

**Step 2 — make the script executable (one-time):**
```bash
chmod +x tools/memory_profile_streamlit.sh
```

**Step 3 — run each scenario:**
```bash
# Athlete idle baseline (30s, no interaction)
./tools/memory_profile_streamlit.sh athlete-idle 30 2 <PID_A>

# Athlete typical interactions (60s — navigate workout view, refresh a few times)
./tools/memory_profile_streamlit.sh athlete-typical 60 2 <PID_A>

# Athlete worst-case (90s — trigger all visible data loads)
./tools/memory_profile_streamlit.sh athlete-worst-case 90 2 <PID_A>

# Admin idle baseline only
./tools/memory_profile_streamlit.sh admin-idle 30 2 <PID_ADM>

# Both apps — athlete typical while admin is idle
./tools/memory_profile_streamlit.sh both-typical 60 2 <PID_A> <PID_ADM>

# Both apps — athlete worst-case while admin is idle
./tools/memory_profile_streamlit.sh both-worst-case 90 2 <PID_A> <PID_ADM>
```

Reports are saved automatically to `tools/reports/` with a timestamp prefix.

### Reading the verdict

Each report ends with a capacity verdict that accounts for estimated Streamlit Cloud runtime overhead (~180 MB):

| Verdict | Estimated Cloud usage |
| --- | --- |
| ✅ SAFE | ≤ 700 MB — well within 1 GB |
| ⚠️ CAUTION | 701–900 MB — monitor closely |
| 🔴 UNSAFE | > 900 MB — likely to exceed limit |

### Capacity snapshot template

Record results here after each profiling session:

| Date | Scenario | Process 1 peak | Process 2 peak | Combined peak | Cloud est. | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| YYYY-MM-DD | athlete-idle | MB | — | — | MB | |
| YYYY-MM-DD | athlete-typical | MB | — | — | MB | |
| YYYY-MM-DD | athlete-worst-case | MB | — | — | MB | |
| YYYY-MM-DD | admin-idle | — | MB | — | MB | |
| YYYY-MM-DD | both-typical | MB | MB | MB | MB | |
| YYYY-MM-DD | both-worst-case | MB | MB | MB | MB | |

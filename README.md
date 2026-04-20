# TheAssembly

TheAssembly is a privacy-first fitness whiteboard built for Streamlit Community Cloud.

## What it does
- **Athlete view:** shows only the current workout window - tomorrow during the 8:00 PM preview or today during the overnight session.
- **Self-wipe:** shows a high-contrast `Garage Closed` state from 9:01 AM through 7:59 PM in `America/New_York`.
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
- the current local time in `America/New_York` is between `8:00 PM` and `11:59 PM`
- `current_state.json` is `open`

From `9:01 AM` through `7:59 PM`, the athlete view always shows **Garage Closed**.

Organizer staging saves the new workout and resets `current_state.json` back to `open`.

## Run locally
```bash
streamlit run streamlit_app.py
```

## Test locally
```bash
python3 -m unittest discover -s tests
```

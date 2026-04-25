# Gym Config Checklist

Use this checklist when setting up a new TheAssembly deployment. Fill in each value before opening Streamlit secrets.

---

## Your data repo

- [ ] Created private GitHub repo for workout data
- Repo owner (GitHub username or org): `_______________`
- Repo name: `_______________`
- Default branch: `_______________` (usually `main` or `master`)
- File path for workouts: `workouts.json` (change only if customized)
- File path for state: `current_state.json` (change only if customized)

---

## GitHub tokens

- [ ] Created read-only PAT for athlete app
  - Token name: `TheAssembly-athlete-read`
  - Permissions: Contents — Read-only
  - Copy token value: `_______________`

- [ ] Created read+write PAT for admin app
  - Token name: `TheAssembly-admin-write`
  - Permissions: Contents — Read and write
  - Copy token value: `_______________`

- [ ] Token expiration date noted (set calendar reminder to rotate):
  `_______________`

---

## App settings

- Admin password (keep private): `_______________`
- Timezone (`APP_TIMEZONE`): `_______________`
  - See [SETUP.md](SETUP.md#timezone-reference) for a list of valid values

---

## Streamlit Cloud — Athlete app secrets

Copy-paste template (fill in your values from above):

```toml
GITHUB_READ_TOKEN = ""
WORKOUTS_REPO_OWNER = ""
WORKOUTS_REPO_NAME = ""
WORKOUTS_REPO_BRANCH = ""
WORKOUTS_FILE_PATH = "workouts.json"
CURRENT_STATE_FILE_PATH = "current_state.json"
APP_TIMEZONE = "America/New_York"
ADMIN_PASSWORD = ""
```

## Streamlit Cloud — Admin app secrets

Same as above but use your write token:

```toml
GITHUB_WRITE_TOKEN = ""
WORKOUTS_REPO_OWNER = ""
WORKOUTS_REPO_NAME = ""
WORKOUTS_REPO_BRANCH = ""
WORKOUTS_FILE_PATH = "workouts.json"
CURRENT_STATE_FILE_PATH = "current_state.json"
APP_TIMEZONE = "America/New_York"
ADMIN_PASSWORD = ""
```

---

## Post-deployment verification

- [ ] Athlete app URL loads with no red error banners
- [ ] Admin app — sidebar password works and Organizer Console appears
- [ ] Staged a test workout and it saved without errors
- [ ] Athlete app reflects staged workout during the correct time window

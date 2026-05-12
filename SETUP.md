# Gym Owner Setup Guide

This guide walks you through deploying your own TheAssembly whiteboard from scratch — no coding required beyond copy-paste.

**Time to complete:** ~20 minutes

---

## What you'll have when done

- **Athlete app** — a clean URL your athletes visit to see today's workout
- **Admin app** — a password-protected URL where you stage workouts

Both apps are free to host on Streamlit Community Cloud.

---

## Step 1 — Create your app repo from the template

1. Go to [TheAssembly on GitHub](https://github.com/your-org/TheAssembly) *(replace with your actual URL)*
2. Click the green **"Use this template"** button → **"Create a new repository"**
3. Name it `TheAssembly` (or anything you like)
4. Set it to **Public** (required for free Streamlit Cloud hosting)
5. Click **"Create repository"**

> ⚠️ Do **not** fork — use the template button. Forking links your repo to ours; the template gives you a clean, independent copy.

---

## Step 2 — Create your private data repo

Your workout data lives in a **separate private repo** — completely isolated from your app code and from everyone else's data.

1. Go to [TheAssemblyData-template on GitHub](https://github.com/your-org/TheAssemblyData-template) *(replace with your actual URL)*
2. Click **"Use this template"** → **"Create a new repository"**
3. Name it `YourGymName-data` (any name works)
4. Set it to **Private** ← important: this keeps your programming private
5. Click **"Create repository"**

The template gives you a starter `workouts.json` (empty) and `current_state.json` (open).

---

## Step 3 — Create a GitHub Personal Access Token (PAT)

The app needs a token to read (and write) your private data repo.

### Recommended: two tokens (tighter security)

**Read-only token** (for athlete app):
1. GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens**
2. Click **"Generate new token"**
3. Token name: `TheAssembly-athlete-read`
4. Expiration: 1 year (set a reminder to rotate)
5. Resource owner: your account
6. Repository access: **Only select repositories** → select `YourGymName-data`
7. Permissions → Repository permissions → **Contents: Read-only**
8. Click **"Generate token"** and copy it immediately

**Read+Write token** (for admin app): repeat the same steps but set **Contents: Read and write**. Name it `TheAssembly-admin-write`.

### Simpler: one token for both

Create one fine-grained token with **Contents: Read and write**. Use it for both apps. Slightly less secure but easier to manage.

---

## Step 4 — Deploy the athlete app to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub
2. Click **"New app"**
3. Repository: select your TheAssembly repo
4. Branch: `master`
5. Main file path: `athlete_app.py`
6. Click **"Advanced settings"** → **Secrets** and paste:

```toml
GITHUB_READ_TOKEN = "github_pat_your_read_only_token_here"
WORKOUTS_REPO_OWNER = "your_github_username"
WORKOUTS_REPO_NAME = "YourGymName-data"
WORKOUTS_REPO_BRANCH = "main"
WORKOUTS_FILE_PATH = "workouts.json"
CURRENT_STATE_FILE_PATH = "current_state.json"
APP_TIMEZONE = "America/New_York"
ADMIN_PASSWORD = "choose_a_strong_password"
```

> Replace every value in quotes. `WORKOUTS_REPO_OWNER` is your GitHub username or org name.

7. Click **"Deploy"** — the app builds in ~2 minutes

---

## Step 5 — Deploy the admin app to Streamlit Cloud

Repeat Step 4 with these differences:
- Main file path: `admin_app.py`
- Replace `GITHUB_READ_TOKEN` with `GITHUB_WRITE_TOKEN` (your read+write token)
- Use the same `ADMIN_PASSWORD` you set for the athlete app

---

## Step 6 — Verify everything works

**Athlete app:**
- Open the athlete URL
- Confirm you see "Garage Closed" (expected when no workouts are staged)
- No red error banners should appear

**Admin app:**
- Open the admin URL
- In the sidebar, enter your `ADMIN_PASSWORD` and click "Unlock admin"
- The Organizer Console should appear below the athlete view
- Stage a test workout and confirm it saves without errors

---

## Step 7 — Share with your athletes

Share only the **athlete app URL**. Keep the admin URL private. Athletes never need a GitHub account.

---

## Timezone reference

Common values for `APP_TIMEZONE`:

| Region | Value |
|---|---|
| US Eastern | `America/New_York` |
| US Central | `America/Chicago` |
| US Mountain | `America/Denver` |
| US Pacific | `America/Los_Angeles` |
| UK | `Europe/London` |
| Central Europe | `Europe/Berlin` |
| Australia East | `Australia/Sydney` |

---

## Troubleshooting

**"GitHub authentication failed (401)"**
- Check your token is pasted with no extra spaces or label text
- Verify the token hasn't expired
- Confirm the token has Contents access to your data repo

**"GitHub data was not found (404)"**
- Double-check `WORKOUTS_REPO_OWNER`, `WORKOUTS_REPO_NAME`, and `WORKOUTS_REPO_BRANCH` match your repo exactly
- Ensure the token has access to the repository (not just your account)

**Athlete app shows Garage Closed unexpectedly**
- Check the current ET time: Garage Closed is expected 11:00 AM – 3:59 PM ET
- Verify `current_state.json` in your data repo contains `{"status": "open"}`
- Confirm a workout exists for today's date with a `status` of `scheduled` or `released`

**Admin console doesn't appear**
- Confirm you set `ADMIN_PASSWORD` in the admin app's Streamlit secrets
- Confirm you entered the password in the sidebar and clicked "Unlock admin"

---

## Optional: Generate Workout Images via Docker (No Local pip install)

If you prefer not to install Python packages locally, run image generation in Docker using the app container dependencies.

1. Ensure your local env file (for example `docker-compose.override.env`) includes:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_IMAGE_MODEL=gemini-2.5-flash-preview-04-17
GEMINI_IMAGE_ASPECT_RATIO=16:9
```

2. Run generation from the repository root:

```bash
docker compose --env-file docker-compose.override.env run --rm app \
	python tools/generate_workout_image.py --date 2026-05-01 --mode gemini --fallback prompt
```

The generated files are written to `../TheAssemblyData/photos/ai/` (or fallback prompt text when quota is exhausted).

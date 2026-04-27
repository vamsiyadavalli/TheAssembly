"""jokes.py — Fetch a safe, family-friendly Joke of the Day from JokeAPI v2.

Uses the two-part setup/delivery format with safe-mode and a strict blacklist
so output is appropriate for all ages including school-age visitors.
Returns None on any network or parsing failure so callers can show fallback copy.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

# Safe two-part joke from any category, explicit content blocked.
_JOKEAPI_URL = (
    "https://v2.jokeapi.dev/joke/Any"
    "?safe-mode"
    "&blacklistFlags=nsfw,racist,sexist,explicit,religious,political"
    "&type=twopart"
)


@dataclass(frozen=True)
class DailyJoke:
    setup: str
    delivery: str
    category: str


def fetch_daily_joke() -> DailyJoke | None:
    """Fetch one safe two-part joke.  Returns None on any failure."""
    try:
        response = requests.get(_JOKEAPI_URL, timeout=6)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    if not isinstance(data, dict) or data.get("error"):
        return None

    setup = str(data.get("setup", "")).strip()
    delivery = str(data.get("delivery", "")).strip()
    category = str(data.get("category", "")).strip()

    if not setup or not delivery:
        return None

    return DailyJoke(setup=setup, delivery=delivery, category=category)

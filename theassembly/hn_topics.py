from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
import html
import re
from typing import Any

import requests


_FIREBASE_API_BASE = "https://hacker-news.firebaseio.com/v0"
_ALGOLIA_ITEM_API_BASE = "https://hn.algolia.com/api/v1/items"

_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "been",
    "being",
    "between",
    "both",
    "comment",
    "comments",
    "could",
    "discussion",
    "from",
    "have",
    "just",
    "more",
    "most",
    "news",
    "only",
    "other",
    "people",
    "really",
    "should",
    "some",
    "still",
    "than",
    "that",
    "their",
    "them",
    "there",
    "they",
    "this",
    "those",
    "topic",
    "very",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
}


@dataclass(frozen=True)
class HNTopic:
    story_id: int
    title: str
    url: str
    points: int
    comments: int
    rank: int

    @property
    def hn_link(self) -> str:
        return f"https://news.ycombinator.com/item?id={self.story_id}"

    @property
    def display_url(self) -> str:
        return self.url or self.hn_link


@dataclass(frozen=True)
class HNConversationStarter:
    top_topics: tuple[HNTopic, ...]
    selected_topic: HNTopic
    summary: str
    refreshed_at_utc: str


def _compute_engagement(points: int, comments: int, comments_weight: float = 1.5) -> float:
    return float(points) + (float(comments) * comments_weight)


def _strip_html(raw_text: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", raw_text)
    normalized_space = re.sub(r"\s+", " ", html.unescape(no_tags)).strip()
    return normalized_space


def _extract_keywords(comment_texts: list[str], max_keywords: int = 3) -> list[str]:
    counter: Counter[str] = Counter()
    for text in comment_texts:
        for token in re.findall(r"[A-Za-z][A-Za-z0-9\-]{3,}", text.lower()):
            if token in _STOPWORDS:
                continue
            counter[token] += 1

    keywords = [word for word, _ in counter.most_common(max_keywords)]
    return keywords


def _summarize_discussion(title: str, comment_texts: list[str]) -> str:
    if not comment_texts:
        return (
            "HN commenters are actively discussing tradeoffs, real-world implications, "
            "and practical next steps around this story."
        )

    keywords = _extract_keywords(comment_texts)
    if not keywords:
        return (
            "The thread has strong engagement, with commenters debating practical impacts, "
            "risks, and how this might play out in real teams."
        )

    if len(keywords) == 1:
        topic_words = keywords[0]
    elif len(keywords) == 2:
        topic_words = f"{keywords[0]} and {keywords[1]}"
    else:
        topic_words = f"{keywords[0]}, {keywords[1]}, and {keywords[2]}"

    return (
        f"Discussion around \"{title}\" is focused on {topic_words}, with a mix of "
        "agreement, pushback, and concrete examples from people sharing field experience."
    )


def _get_json(url: str, timeout_seconds: int = 8) -> Any:
    response = requests.get(url, timeout=timeout_seconds)
    response.raise_for_status()
    return response.json()


def _load_story_candidates(max_candidates: int = 30) -> list[HNTopic]:
    story_ids = _get_json(f"{_FIREBASE_API_BASE}/topstories.json")
    if not isinstance(story_ids, list):
        return []

    topics: list[HNTopic] = []
    for idx, story_id in enumerate(story_ids[:max_candidates], start=1):
        if not isinstance(story_id, int):
            continue

        try:
            item = _get_json(f"{_FIREBASE_API_BASE}/item/{story_id}.json")
        except Exception:
            continue

        if not isinstance(item, dict):
            continue
        if item.get("type") != "story":
            continue
        if item.get("dead") or item.get("deleted"):
            continue

        title = str(item.get("title", "")).strip()
        if not title:
            continue

        points = int(item.get("score", 0) or 0)
        comments = int(item.get("descendants", 0) or 0)
        url = str(item.get("url", "")).strip()

        topics.append(
            HNTopic(
                story_id=story_id,
                title=title,
                url=url,
                points=points,
                comments=comments,
                rank=idx,
            )
        )

    return topics


def _select_top_topics(candidates: list[HNTopic], top_n: int = 3, comments_weight: float = 1.5) -> list[HNTopic]:
    ranked = sorted(
        candidates,
        key=lambda topic: (
            _compute_engagement(topic.points, topic.comments, comments_weight),
            topic.comments,
            topic.points,
            -topic.rank,
        ),
        reverse=True,
    )
    return ranked[:top_n]


def _collect_comment_texts(story_id: int, max_comments: int = 40) -> list[str]:
    try:
        item_payload = _get_json(f"{_ALGOLIA_ITEM_API_BASE}/{story_id}")
    except Exception:
        return []

    if not isinstance(item_payload, dict):
        return []

    texts: list[str] = []
    queue: deque[dict[str, Any]] = deque()
    children = item_payload.get("children", [])
    if isinstance(children, list):
        for child in children:
            if isinstance(child, dict):
                queue.append(child)

    while queue and len(texts) < max_comments:
        node = queue.popleft()
        raw_text = str(node.get("text", "")).strip()
        clean_text = _strip_html(raw_text)
        if clean_text:
            texts.append(clean_text)

        nested = node.get("children", [])
        if isinstance(nested, list):
            for child in nested:
                if isinstance(child, dict):
                    queue.append(child)

    return texts


def fetch_hn_conversation_starter(
    max_candidates: int = 30,
    top_n: int = 3,
    comments_weight: float = 1.5,
) -> HNConversationStarter | None:
    try:
        candidates = _load_story_candidates(max_candidates=max_candidates)
    except Exception:
        return None

    if not candidates:
        return None

    top_topics = _select_top_topics(candidates, top_n=top_n, comments_weight=comments_weight)
    if not top_topics:
        return None

    selected = top_topics[0]
    comment_texts = _collect_comment_texts(selected.story_id)
    summary = _summarize_discussion(selected.title, comment_texts)
    refreshed_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return HNConversationStarter(
        top_topics=tuple(top_topics),
        selected_topic=selected,
        summary=summary,
        refreshed_at_utc=refreshed_at_utc,
    )

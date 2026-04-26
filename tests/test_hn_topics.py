import unittest

from theassembly.hn_topics import HNTopic, _compute_engagement, _select_top_topics, _summarize_discussion


class HNTopicsTests(unittest.TestCase):
    def test_engagement_weights_comments(self) -> None:
        engagement = _compute_engagement(points=100, comments=20, comments_weight=1.5)
        self.assertEqual(130.0, engagement)

    def test_select_top_topics_orders_by_engagement_then_tiebreakers(self) -> None:
        topics = [
            HNTopic(story_id=1, title="A", url="https://a", points=100, comments=10, rank=1),
            HNTopic(story_id=2, title="B", url="https://b", points=70, comments=40, rank=2),
            HNTopic(story_id=3, title="C", url="https://c", points=150, comments=0, rank=3),
            HNTopic(story_id=4, title="D", url="https://d", points=80, comments=20, rank=4),
        ]

        selected = _select_top_topics(topics, top_n=3, comments_weight=1.5)

        self.assertEqual([3, 2, 1], [topic.story_id for topic in selected])

    def test_summarize_discussion_with_comments_mentions_title(self) -> None:
        summary = _summarize_discussion(
            "Example Topic",
            [
                "Developers are debating security and performance tradeoffs.",
                "Lots of concern about reliability and long-term maintenance.",
                "Some teams report productivity gains, others report regressions.",
            ],
        )

        self.assertIn("Example Topic", summary)
        self.assertIn("Discussion", summary)

    def test_summarize_discussion_without_comments_fallback(self) -> None:
        summary = _summarize_discussion("Any Topic", [])

        self.assertIn("actively discussing", summary)


if __name__ == "__main__":
    unittest.main()

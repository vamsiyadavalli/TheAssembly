from __future__ import annotations

import unittest
from unittest.mock import patch

from theassembly.langgraph_pipeline.nodes import critic_node
from theassembly.langgraph_pipeline.text_agent import TextAgentResult


class Tier2CriticStarterTests(unittest.TestCase):
    def _base_state(self) -> dict:
        return {
            "candidate_graphic_prompt": "Poster prompt",
            "semantic_contract": "contract",
            "panel_budgets": {},
            "api_key": "test-key",
            "critic_model": "models/gemini-2.5-pro",
            "critic_enabled": True,
            "critic_temperature": 0.0,
            "critic_max_output_tokens": 1000,
            "retry_count": 0,
            "save_intermediate_prompts": False,
            "node_traces": {},
            "error_log": [],
        }

    def test_default_behavior_compatible_with_score_70(self) -> None:
        state = self._base_state()
        payload = {
            "pass": True,
            "score_0_to_100": 70,
            "blockers": [],
            "warnings": [],
            "required_fixes": [],
            "hallucination_risk": {
                "added_content_risk": "medium",
                "dropped_content_risk": "low",
                "reorder_risk": "low",
                "truncation_risk": "low",
            },
            "confidence": 0.9,
        }
        with patch(
            "theassembly.langgraph_pipeline.nodes.call_text_agent",
            return_value=TextAgentResult(payload=payload, model="models/gemini-2.5-pro", usage={}),
        ):
            result = critic_node(state)

        self.assertEqual(result["final_graphic_prompt"], "Poster prompt")
        self.assertEqual(result["critic_score"], 70)

    def test_tier2_starter_enforces_min_score(self) -> None:
        state = self._base_state()
        state["tier2_starter_enabled"] = True
        state["critic_min_score"] = 85

        payload = {
            "pass": True,
            "score_0_to_100": 80,
            "blockers": [],
            "warnings": [],
            "required_fixes": [],
            "hallucination_risk": {
                "added_content_risk": "low",
                "dropped_content_risk": "low",
                "reorder_risk": "low",
                "truncation_risk": "low",
            },
            "confidence": 0.9,
        }
        with patch(
            "theassembly.langgraph_pipeline.nodes.call_text_agent",
            return_value=TextAgentResult(payload=payload, model="models/gemini-2.5-pro", usage={}),
        ):
            result = critic_node(state)

        self.assertEqual(result["final_graphic_prompt"], "")
        self.assertIn("critic rejected prompt", result["feedback"])

    def test_tier2_starter_enforces_low_added_content_risk(self) -> None:
        state = self._base_state()
        state["tier2_starter_enabled"] = True
        state["critic_min_score"] = 85

        payload = {
            "pass": True,
            "score_0_to_100": 90,
            "blockers": [],
            "warnings": [],
            "required_fixes": [],
            "hallucination_risk": {
                "added_content_risk": "medium",
                "dropped_content_risk": "low",
                "reorder_risk": "low",
                "truncation_risk": "low",
            },
            "confidence": 0.9,
        }
        with patch(
            "theassembly.langgraph_pipeline.nodes.call_text_agent",
            return_value=TextAgentResult(payload=payload, model="models/gemini-2.5-pro", usage={}),
        ):
            result = critic_node(state)

        self.assertEqual(result["final_graphic_prompt"], "")
        self.assertIn("added_content_risk=medium", result["feedback"])


if __name__ == "__main__":
    unittest.main()

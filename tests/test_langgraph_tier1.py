from __future__ import annotations

import unittest
from unittest.mock import patch

from theassembly.langgraph_pipeline.nodes import reasoning_node
from theassembly.langgraph_pipeline.text_agent import TextAgentError, TextAgentResult


class Tier1ReasoningTests(unittest.TestCase):
    def _base_state(self) -> dict:
        return {
            "raw_wod": {
                "content": "For time",
                "stimulus": "High-Intensity Grit",
                "movements": [
                    {"name": "Turkish Get-Up", "reps": "8", "section": "Main"},
                    {"name": "Run", "reps": "400m", "section": "Finisher"},
                ],
            },
            "feedback": "",
            "api_key": "test-key",
            "reasoning_model": "models/gemini-2.5-flash",
            "reasoning_temperature": 0.1,
            "reasoning_max_output_tokens": 1200,
            "reasoning_schema_version": "tier1_staged",
            "retry_count": 0,
            "save_intermediate_prompts": False,
            "node_traces": {},
            "llm_models": {},
            "llm_usage": {},
        }

    def test_staged_reasoning_calls_three_agents(self) -> None:
        state = self._base_state()
        side_effect = [
            TextAgentResult(
                payload={
                    "workout_archetype": "for_time",
                    "intensity_profile": "high",
                    "confidence": 0.9,
                },
                model="models/gemini-2.5-flash",
                usage={"total_token_count": 100},
            ),
            TextAgentResult(
                payload={
                    "layout_strategy": "split_pane",
                    "finisher_strategy": "right_sidebar",
                    "visual_goal": "Crisp high-contrast structure",
                    "rationale": "Finisher exists so preserve dedicated lane.",
                },
                model="models/gemini-2.5-flash",
                usage={"total_token_count": 120},
            ),
            TextAgentResult(
                payload={
                    "risk_flags": [{"code": "ocr_risk", "severity": "medium", "message": "Use legible text."}],
                    "retry_directives": [],
                    "non_negotiables": [
                        "preserve_row_order",
                        "preserve_row_count",
                        "preserve_reps_exactly",
                        "preserve_movement_names_exactly",
                    ],
                    "section_priority": ["header", "main_movements", "finisher", "footer"],
                },
                model="models/gemini-2.5-flash",
                usage={"total_token_count": 140},
            ),
        ]
        with patch("theassembly.langgraph_pipeline.nodes.call_text_agent", side_effect=side_effect) as mock_call:
            result = reasoning_node(state)

        self.assertEqual(mock_call.call_count, 3)
        self.assertEqual(result["reasoning_plan"]["layout_strategy"], "split_pane")
        self.assertEqual(result["reasoning_schema_version"], "tier1_staged")
        self.assertIn("reasoning_stage_classification", result)
        self.assertIn("reasoning_stage_layout", result)
        self.assertIn("reasoning_stage_risks", result)

    def test_staged_reasoning_falls_back_per_stage(self) -> None:
        state = self._base_state()
        with patch("theassembly.langgraph_pipeline.nodes.call_text_agent", side_effect=TextAgentError("json parse failed")):
            result = reasoning_node(state)

        self.assertEqual(result["reasoning_schema_version"], "tier1_staged")
        self.assertIn("reasoning_plan", result)
        self.assertTrue(result["reasoning_plan"]["layout_strategy"] in {"split_pane", "masonry_2col", "vertical_stack"})
        trace = result["node_traces"]["reasoning"]
        self.assertGreaterEqual(len(trace["warnings"]), 1)


if __name__ == "__main__":
    unittest.main()

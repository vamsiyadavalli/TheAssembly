from __future__ import annotations

import unittest
from unittest.mock import patch

from theassembly.langgraph_pipeline.nodes import nutrition_baseline_node, reasoning_node
from theassembly.langgraph_pipeline.recipe_rotation import select_recipes_deterministic
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


class NutritionBaselineTests(unittest.TestCase):
    def _base_state(self) -> dict:
        return {
            "raw_wod": {
                "date": "2026-05-15",
                "content": "For time",
                "stimulus": "High output mixed modal",
            },
            "validated_wod": {"stimulus": "High output mixed modal"},
            "reasoning_plan": {
                "workout_archetype": "for_time",
                "intensity_profile": "high",
            },
            "api_key": "test-key",
            "reasoning_model": "models/gemini-2.5-flash",
            "reasoning_temperature": 0.1,
            "reasoning_max_output_tokens": 1200,
            "retry_count": 0,
            "save_intermediate_prompts": False,
            "node_traces": {},
            "llm_models": {},
            "llm_usage": {},
        }

    def test_recipe_rotation_is_stable(self) -> None:
        first = select_recipes_deterministic("2026-05-15", "for_time", "high")
        second = select_recipes_deterministic("2026-05-15", "for_time", "high")
        alternate = select_recipes_deterministic("2026-05-16", "for_time", "high")

        self.assertEqual(first, second)
        self.assertNotEqual(first, alternate)
        self.assertEqual(["cook_at_home", "quick_order_salad_bar"], [item["category"] for item in first])

    def test_nutrition_node_overrides_recipe_ideas_deterministically(self) -> None:
        state = self._base_state()
        payload = {
            "training_day_type": "high_intensity",
            "calorie_guidance": 2600,
            "protein_target_g": 180,
            "carbs_target_g": 280,
            "fat_target_g": 75,
            "pre_workout_fuel": "Banana and yogurt 60 minutes before class.",
            "post_workout_fuel": "Protein and rice within two hours.",
            "hydration_ml": 3200,
            "electrolytes_mg_sodium": 900,
            "meal_timing_strategy": "Anchor carbs around training and protein across the day.",
            "rationale": "High-output training days need glycogen support and consistent protein.",
            "disclaimer": "Consult a registered dietitian for personalized advice.",
            "recipe_ideas": [
                {"title": "Placeholder 1", "fit_reason": "Placeholder reason 1", "source_link": "https://example.com/1", "category": "cook_at_home"},
                {"title": "Placeholder 2", "fit_reason": "Placeholder reason 2", "source_link": "https://example.com/2", "category": "quick_order_salad_bar"},
            ],
            "confidence": 0.84,
        }

        with patch(
            "theassembly.langgraph_pipeline.nodes.call_text_agent",
            return_value=TextAgentResult(payload=payload, model="models/gemini-2.5-flash", usage={"total_token_count": 88}),
        ):
            result = nutrition_baseline_node(state)

        recipes = result["nutrition_baseline"]["recipe_ideas"]
        self.assertEqual(select_recipes_deterministic("2026-05-15", "for_time", "high"), recipes)
        self.assertEqual("success", result["nutrition_generation_status"])
        self.assertEqual(2, len(recipes))

    def test_nutrition_node_recovers_after_initial_json_failure(self) -> None:
        state = self._base_state()
        recovered_payload = {
            "training_day_type": "high_intensity",
            "calorie_guidance": 2700,
            "protein_target_g": 175,
            "carbs_target_g": 300,
            "fat_target_g": 80,
            "pre_workout_fuel": "Toast and fruit.",
            "post_workout_fuel": "Rice bowl with protein.",
            "hydration_ml": 3400,
            "electrolytes_mg_sodium": 1100,
            "meal_timing_strategy": "Carbs around training windows.",
            "rationale": "Recovery path payload.",
            "disclaimer": "Consult a registered dietitian for personalized advice.",
            "recipe_ideas": [
                {"title": "Placeholder 1", "fit_reason": "x", "source_link": "https://example.com/1", "category": "cook_at_home"},
                {"title": "Placeholder 2", "fit_reason": "y", "source_link": "https://example.com/2", "category": "quick_order_salad_bar"},
            ],
            "confidence": 0.7,
        }

        with patch(
            "theassembly.langgraph_pipeline.nodes.call_text_agent",
            side_effect=[
                TextAgentError("text agent returned non-JSON output"),
                TextAgentResult(payload=recovered_payload, model="models/gemini-2.5-flash", usage={"total_token_count": 99}),
            ],
        ):
            result = nutrition_baseline_node(state)

        self.assertEqual("recovered", result["nutrition_generation_status"])
        self.assertTrue(result["nutrition_baseline"])
        self.assertEqual(2, len(result["nutrition_baseline"]["recipe_ideas"]))

    def test_nutrition_node_uses_deterministic_fallback_when_llm_unparseable(self) -> None:
        state = self._base_state()
        with patch(
            "theassembly.langgraph_pipeline.nodes.call_text_agent",
            side_effect=[
                TextAgentError("bad json 1"),
                TextAgentError("bad json 2"),
            ],
        ):
            result = nutrition_baseline_node(state)

        baseline = result["nutrition_baseline"]
        self.assertEqual("fallback", result["nutrition_generation_status"])
        self.assertTrue(baseline)
        self.assertEqual("high_intensity", baseline["training_day_type"])
        self.assertEqual(2, len(baseline["recipe_ideas"]))


if __name__ == "__main__":
    unittest.main()

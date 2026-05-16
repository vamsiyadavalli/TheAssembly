---
name: langgraph-pipeline
description: Understand, debug, and extend the TheAssembly workout poster LangGraph pipeline. Use when working on node orchestration, state contracts, retry behavior, validation mismatches, or tool-level deterministic logic.
compatibility: Designed for TheAssembly repository workflows; requires Python and access to the local repo files.
metadata:
  owner: theassembly
  domain: workout-poster-generation
  version: "1.0"
---

# LangGraph Pipeline Skill

Use this skill when a task involves the workout poster generation pipeline, especially node ordering, state contracts, OCR validation failures, and retries.

## Scope

- Analyze and modify pipeline orchestration in `theassembly/langgraph_pipeline/graph.py`.
- Analyze and modify node behavior in `theassembly/langgraph_pipeline/nodes.py`.
- Analyze and modify deterministic tools in `theassembly/langgraph_pipeline/tools.py`.
- Keep state contracts aligned in `theassembly/langgraph_pipeline/state.py`.

## Current Node Flow

1. `reasoning_node`
2. `editor_node`
3. `architect_node`
4. `nutrition_baseline_node`
5. `designer_node`
6. `critic_node`
7. `generator_node`
8. `validation_node`

Retry path: `validation_node` -> `reasoning_node` when validation fails and retries remain.

## Deterministic Tool Contracts

### `validate_workout_schema`
- Input: raw workout object.
- Output: normalized validated workout object.
- Guarantees required fields and contiguous grouping constraints.
- Failure mode: raises `ToolExecutionError`.

### `generate_coordinate_map`
- Input: validated workout object.
- Output: deterministic coordinate manifest.
- Guarantees stable panel/zone computations.
- Failure mode: raises `ToolExecutionError`.

### `get_brand_assets`
- Input: stimulus string.
- Output: deterministic style tokens.
- Failure mode: returns safe defaults.

### `verify_image_accuracy`
- Input: image path + expected movement facts.
- Output: `is_valid`, `similarity_score`, `mismatches`.
- Failure mode: raises `ToolExecutionError` when OCR backend is unavailable.

## State Contract

When changing nodes, keep producer/consumer keys aligned in `PosterState`:

- Reasoning writes strategy/plan used by downstream nodes.
- Editor writes `validated_wod`, `canonical_rows`, `semantic_contract`.
- Architect writes `layout_coordinates`, `panel_budgets`, `overflow_risks`.
- Designer writes candidate/final prompt artifacts.
- Critic writes score/review and may block generation.
- Generator writes `image_path`, `image_metrics`.
- Validator writes `validation_result`, `similarity_score`, `feedback`, retry metadata.

## Failure And Retry Guidance

- Validation failures should be actionable and structured.
- Retry history should include reason and timestamp.
- Keep retry logic deterministic in `should_retry`.

## Editing Checklist

1. Update `graph.py` node order and conditional edges if orchestration changes.
2. Update `state.py` when adding/removing node outputs.
3. Update `SKILL.md` files when behavior contracts change.
4. Keep docs aligned: `docs/ARCHITECTURE.md` and `LANGGRAPH_IMPLEMENTATION_COMPLETE.md`.

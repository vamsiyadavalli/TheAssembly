# LangGraph Pipeline — Package Notes

Developer-facing notes for the `theassembly.langgraph_pipeline` Python package.

> **This is not an agent skill.** The canonical, AgentSkills.io-compliant skill lives at
> [`.github/skills/langgraph-pipeline/SKILL.md`](../../.github/skills/langgraph-pipeline/SKILL.md).
> Agents should load that file; this README exists only as code-adjacent reference for humans editing the module.

## Current LangGraph Flow

1. `reasoning_node`
2. `editor_node`
3. `architect_node`
4. `nutrition_baseline_node`
5. `designer_node`
6. `critic_node`
7. `generator_node`
8. `validation_node`

Retry edge: `validation_node` routes to `reasoning_node` when validation fails and retries remain.

## Deterministic Tool Registry

### Skill 1: `validate_workout_schema`
- Target Node: `editor_node`
- Input: raw workout object
- Output: normalized validated workout object
- Guarantees:
  - every movement has `name` and `reps`
  - optional fields are correctly typed
  - grouping constraints remain contiguous
- Failure Mode: raises `ToolExecutionError`

### Skill 2: `generate_coordinate_map`
- Target Node: `architect_node`
- Input: validated workout object
- Output: deterministic coordinate manifest
- Guarantees:
  - deterministic zone and panel coordinates
  - stable layout computation based on movement data
- Failure Mode: raises `ToolExecutionError`

### Skill 3: `get_brand_assets`
- Target Node: `designer_node`
- Input: stimulus string
- Output: deterministic style tokens
- Guarantees:
  - returns reusable palette/typography/lighting tokens
- Failure Mode: returns defaults when no profile matches

### Skill 4: `verify_image_accuracy`
- Target Node: `validation_node`
- Input: image path + expected movement facts
- Output: validation dict with `is_valid`, `similarity_score`, `mismatches`
- Guarantees:
  - OCR-derived comparison against expected workout facts
  - mismatch output suitable for retry feedback
- Failure Mode: raises `ToolExecutionError` if OCR backend is unavailable

## State Contract Highlights

- `editor_node` writes `validated_wod`, `canonical_rows`, `semantic_contract`
- `architect_node` writes `layout_coordinates`, `panel_budgets`, `overflow_risks`
- `designer_node` writes prompt artifacts
- `critic_node` writes score and review artifacts
- `generator_node` writes `image_path`, `image_metrics`
- `validation_node` writes `validation_result`, `similarity_score`, `feedback`, retry metadata

## Testability Contract

- Deterministic tools are unit-testable without external API calls.
- `verify_image_accuracy` supports deterministic testing via injected OCR behavior.
- Retry logic is controlled through state and `should_retry`.

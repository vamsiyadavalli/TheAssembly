# TheAssembly Agents Guide

This file is the repository-level guide for agentic workflows in TheAssembly.

## Primary Agentic System

The workout poster generator uses a LangGraph pipeline implemented under `theassembly/langgraph_pipeline/`.

### Runtime Flow

1. `reasoning_node`
2. `editor_node`
3. `architect_node`
4. `nutrition_baseline_node`
5. `designer_node`
6. `critic_node`
7. `generator_node`
8. `validation_node`

Conditional retry: `validation_node` routes to `reasoning_node` when validation fails and `retry_count < max_retries`.

## Node Responsibilities

- `reasoning_node`: Builds strategy from workout data and retry feedback.
- `editor_node`: Validates schema and freezes semantic contract.
- `architect_node`: Produces deterministic layout coordinates and panel budgets.
- `nutrition_baseline_node`: Produces non-blocking nutrition artifact.
- `designer_node`: Produces image prompt draft/final candidate.
- `critic_node`: Scores and gates quality before generation.
- `generator_node`: Calls image model and writes output image.
- `validation_node`: OCR compares against canonical rows and drives retries.

## State Contract Source

`PosterState` in `theassembly/langgraph_pipeline/state.py` is the contract source of truth.

When adding or modifying fields:

1. Update producers and consumers in nodes.
2. Update trace outputs in `graph.py`.
3. Update skill docs and architecture docs.

## Deterministic Tool Layer

Tools in `theassembly/langgraph_pipeline/tools.py` should remain deterministic and testable in isolation:

- `validate_workout_schema`
- `generate_coordinate_map`
- `get_brand_assets`
- `verify_image_accuracy`

## Required Documentation Sync

If changing pipeline behavior, also update:

- `.github/skills/langgraph-pipeline/SKILL.md`
- `theassembly/langgraph_pipeline/SKILL.md`
- `docs/ARCHITECTURE.md`
- `LANGGRAPH_IMPLEMENTATION_COMPLETE.md`

## Testing Expectations

- Keep deterministic tool tests runnable without external API access.
- Keep retry behavior observable through state and trace artifacts.
- Ensure quality-gate and retry edge conditions remain covered by tests.

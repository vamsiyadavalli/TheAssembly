# Local Python Tools Registry

This registry defines deterministic local tools used by the LangGraph poster pipeline.

## Skill 1: validate_workout_schema
- Target Node: EditorNode
- Function: validate_workout_schema
- Input: raw workout object
- Output: normalized validated workout object
- Guarantees:
  - every movement has name and reps
  - optional fields are correctly typed
  - round_group_label segments are contiguous
- Failure Mode: raises ToolExecutionError (fail-fast)

## Skill 2: generate_coordinate_map
- Target Node: ArchitectNode
- Function: generate_coordinate_map
- Input: validated workout object
- Output: deterministic 1024x1024 coordinate manifest
- Guarantees:
  - Zone A header, Zone B body, Zone C footer
  - reserves 30 percent right sidebar when Finisher exists
  - safe-zone and movement boxes computed deterministically
- Failure Mode: raises ToolExecutionError (fail-fast)

## Skill 3: get_brand_assets
- Target Node: DesignerNode
- Function: get_brand_assets
- Input: stimulus string
- Output: deterministic style tokens (palette, typography, lighting)
- Guarantees:
  - includes electric blue accent #007BFF
  - maps stimulus to repeatable visual style profile
- Failure Mode: returns defaults if no match

## Skill 4: verify_image_accuracy
- Target Node: ValidationNode
- Function: verify_image_accuracy
- Input: image path + expected movement facts
- Output: validation dict with is_valid, similarity_score, mismatches
- Guarantees:
  - text extracted and compared against name/reps/rx_weight facts
  - score below threshold triggers retry loop
- Failure Mode: ToolExecutionError if OCR backend unavailable

## State Update Contract
- Each node must write its tool output into PosterState keys used by downstream nodes.
- EditorNode writes validated_wod.
- ArchitectNode writes layout_coordinates.
- DesignerNode writes brand_assets and final_graphic_prompt.
- ValidationNode writes validation_result, similarity_score, feedback, is_valid.

## Testability Contract
- Every tool supports isolated unit tests.
- verify_image_accuracy accepts a custom text_extractor for deterministic mocking.
- No Gemini API call is required for tool-only tests.

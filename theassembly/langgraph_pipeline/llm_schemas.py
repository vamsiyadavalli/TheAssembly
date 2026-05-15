from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RiskFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Literal[
        "long_labels",
        "many_rows",
        "mixed_units",
        "duplicate_names",
        "finisher_parts",
        "weight_density",
        "ocr_risk",
        "crowding_risk",
    ]
    severity: Literal["low", "medium", "high"]
    message: str = Field(min_length=5, max_length=200)


class ReasoningPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workout_archetype: Literal["amrap", "emom", "for_time", "strength", "team", "mixed"]
    intensity_profile: Literal["low", "moderate", "high", "mixed"]
    layout_strategy: Literal["vertical_stack", "masonry_2col", "split_pane"]
    finisher_strategy: Literal["none", "right_sidebar", "segmented_sidebar"]
    visual_goal: str = Field(min_length=10, max_length=200)
    section_priority: list[
        Literal[
            "header",
            "subheader",
            "round_labels",
            "main_movements",
            "finisher",
            "footer",
            "technical_cues",
        ]
    ] = Field(min_length=3, max_length=8)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    retry_directives: list[str] = Field(default_factory=list)
    non_negotiables: list[
        Literal[
            "preserve_row_order",
            "preserve_row_count",
            "preserve_reps_exactly",
            "preserve_movement_names_exactly",
            "preserve_finisher_partition",
            "preserve_weights_exactly",
        ]
    ] = Field(min_length=4)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=20, max_length=500)


class WorkoutClassificationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workout_archetype: Literal["amrap", "emom", "for_time", "strength", "team", "mixed"]
    intensity_profile: Literal["low", "moderate", "high", "mixed"]
    confidence: float = Field(ge=0.0, le=1.0)


class LayoutRecommendationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout_strategy: Literal["vertical_stack", "masonry_2col", "split_pane"]
    finisher_strategy: Literal["none", "right_sidebar", "segmented_sidebar"]
    visual_goal: str = Field(min_length=10, max_length=200)
    rationale: str = Field(min_length=20, max_length=500)


class RiskAssessmentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_flags: list[RiskFlag] = Field(default_factory=list)
    retry_directives: list[str] = Field(default_factory=list)
    non_negotiables: list[
        Literal[
            "preserve_row_order",
            "preserve_row_count",
            "preserve_reps_exactly",
            "preserve_movement_names_exactly",
            "preserve_finisher_partition",
            "preserve_weights_exactly",
        ]
    ] = Field(min_length=4)
    section_priority: list[
        Literal[
            "header",
            "subheader",
            "round_labels",
            "main_movements",
            "finisher",
            "footer",
            "technical_cues",
        ]
    ] = Field(min_length=3, max_length=8)


class PanelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    panel_kind: Literal[
        "main_movement",
        "round_group_header",
        "finisher_group_header",
        "finisher_movement",
    ]
    order_index: int = Field(ge=1, le=100)
    heading: str = Field(min_length=1, max_length=120)
    body_lines: list[str] = Field(min_length=1, max_length=6)
    notes_line: str = Field(default="", max_length=200)
    weight_line: str = Field(default="", max_length=200)


class FooterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stimulus_line: str = Field(min_length=1, max_length=220)
    technical_cues: list[str] = Field(default_factory=list, max_length=5)


class ComplianceChecklist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preserves_row_order: Literal[True]
    preserves_row_count: Literal[True]
    preserves_reps_exactly: Literal[True]
    preserves_movement_names_exactly: Literal[True]
    preserves_finisher_partition: Literal[True]
    avoids_unlisted_text: Literal[True]


class DesignerPromptModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_text: str = Field(min_length=5, max_length=120)
    subheader_text: str = Field(min_length=3, max_length=180)
    panel_specs: list[PanelSpec] = Field(min_length=1, max_length=24)
    footer_specs: FooterSpec
    style_directives: list[str] = Field(min_length=4, max_length=20)
    negative_prompt: list[str] = Field(min_length=4, max_length=20)
    compliance_checklist: ComplianceChecklist
    rationale: str = Field(min_length=20, max_length=500)


class CriticFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str = Field(min_length=5, max_length=220)


class CriticBlocker(CriticFinding):
    severity: Literal["medium", "high", "critical"]


class HallucinationRisk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    added_content_risk: Literal["low", "medium", "high"]
    dropped_content_risk: Literal["low", "medium", "high"]
    reorder_risk: Literal["low", "medium", "high"]
    truncation_risk: Literal["low", "medium", "high"]


class CriticReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pass_: bool = Field(alias="pass")
    score_0_to_100: int = Field(ge=0, le=100)
    blockers: list[CriticBlocker] = Field(default_factory=list)
    warnings: list[CriticFinding] = Field(default_factory=list)
    required_fixes: list[str] = Field(default_factory=list)
    hallucination_risk: HallucinationRisk
    confidence: float = Field(ge=0.0, le=1.0)


REASONING_PLAN_SCHEMA = ReasoningPlanModel.model_json_schema()
WORKOUT_CLASSIFICATION_SCHEMA = WorkoutClassificationModel.model_json_schema()
LAYOUT_RECOMMENDATION_SCHEMA = LayoutRecommendationModel.model_json_schema()
RISK_ASSESSMENT_SCHEMA = RiskAssessmentModel.model_json_schema()
DESIGNER_PROMPT_SCHEMA = DesignerPromptModel.model_json_schema()
CRITIC_REVIEW_SCHEMA = CriticReviewModel.model_json_schema()

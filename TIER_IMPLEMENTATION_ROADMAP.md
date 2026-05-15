# Implementation Roadmap: Quality Tier Progression

## Executive Summary

| Tier | Effort | Duration | Cost Impact | Quality Gain | Risk |
|------|--------|----------|-------------|--------------|------|
| **Tier 1** | Medium | 1-2 weeks | +50% cost | 75% → 88% | Low |
| **Tier 2** | Medium | 2-3 weeks | +30% cost | 88% → 91% | Low |
| **Tier 3** | High | 4-6 weeks | +100% cost | 91% → 94% | Medium |
| **Tier 4** | Very High | 8-12 weeks | +200% cost | 94% → 98% | High |

---

## Current Baseline

## Data Contract Safety (Implemented)

- `workouts.json` remains unchanged.
- Tier work is isolated to LangGraph reasoning output schemas, not workout input schema.
- New runtime switch controls tiered schema behavior:
    - `LANGGRAPH_REASONING_SCHEMA_VERSION=v1` (default, existing monolithic reasoning schema)
    - `LANGGRAPH_REASONING_SCHEMA_VERSION=tier1_staged` (new staged reasoning schemas)
- Staged schema payloads are stored in pipeline state as internal fields:
    - `reasoning_stage_classification`
    - `reasoning_stage_layout`
    - `reasoning_stage_risks`


**Codebase:**
- 2,446 total lines across 7 files
- nodes.py: 973 lines (40%)
- tools.py: 301 lines (12%)
- graph.py: 180 lines (7%)
- llm_schemas.py: 142 lines (6%)
- text_agent.py: 120 lines (5%)

**Performance:**
- Reasoning node: ~7s average (with JSON failures)
- Designer node: ~15s average (with fallback)
- Critic node: ~9s average
- Generator node: ~7s average
- Validator node: ~1s average
- **Total pipeline: ~50s per run** (including 15-30s for Gemini image generation)

**Quality Metrics:**
- JSON schema success rate: ~20% (1/5 runs)
- Fallback rate: ~80% (4/5 use heuristics)
- OCR similarity score: 0.74 average (target: 1.0)
- Validation pass rate: ~20% (1/5 runs)

---

# TIER 1: Fix Immediate Failures

## Goal
Increase JSON schema success rate from 20% → 85%+

## Strategy
Decompose complex monolithic schemas into simpler, focused schemas.

### Problem Analysis

**Current Architecture:**
```
ReasoningPlanModel (10 fields, nested RiskFlag list)
  ↓ (single LLM call)
  ? JSON fails (unterminated string, missing delimiter)
  ↓ Falls back to heuristics
  ✗ Loses reasoning quality
```

**Issue:** Gemini's `response_mime_type="application/json"` constraint fails on complex nested structures. The model generates:
```json
{
  "workout_archetype": "amrap",
  "intensity_profile": "high",
  "risk_flags": [
    {"code": "long_labels", "severity": "medium", "message": "text with unterminated "quote}
    // ^ Escaping fails, JSON parsing breaks
```

### Implementation Plan

**Phase 1A: Decompose ReasoningPlanModel (1-2 days)**

Current single schema:
```python
class ReasoningPlanModel(BaseModel):
    workout_archetype: Literal["amrap", "emom", "for_time", ...]
    intensity_profile: Literal["low", "moderate", "high", ...]
    layout_strategy: Literal["vertical_stack", "masonry_2col", ...]
    finisher_strategy: Literal[...]
    visual_goal: str
    section_priority: list[str]
    risk_flags: list[RiskFlag]  # ← Complex nested object
    non_negotiables: list[str]
    confidence: float
    rationale: str
```

Becomes three simpler schemas:

```python
# Schema 1: Classification (simple, high success rate)
class WorkoutClassification(BaseModel):
    workout_archetype: Literal["amrap", "emom", "for_time", ...]
    intensity_profile: Literal["low", "moderate", "high", ...]
    confidence: float

# Schema 2: Layout Strategy (simple, focused)
class LayoutRecommendation(BaseModel):
    layout_strategy: Literal["vertical_stack", "masonry_2col", ...]
    finisher_strategy: Literal["none", "right_sidebar", ...]
    visual_goal: str
    rationale: str

# Schema 3: Risk Assessment (still complex but smaller)
class RiskAssessment(BaseModel):
    risk_flags: list[RiskFlag]
    non_negotiables: list[str]
    section_priority: list[str]
```

**Phase 1B: Implement Staged Reasoning (2-3 days)**

Update `reasoning_node` in nodes.py:
```python
def reasoning_node(state: PosterState) -> PosterState:
    # Stage 1: Simple classification
    classification = call_text_agent(
        system_prompt="Classify this workout",
        user_prompt=f"Workout: {raw_wod}",
        response_model=WorkoutClassification,  # ← Simpler schema
        temperature=0.1,
        max_output_tokens=200,  # ← Fewer tokens needed
    )
    
    # Stage 2: Layout recommendation (uses classification result)
    layout = call_text_agent(
        system_prompt="Recommend layout based on classification",
        user_prompt=f"Archetype: {classification.workout_archetype}\n...",
        response_model=LayoutRecommendation,
        temperature=0.1,
        max_output_tokens=400,
    )
    
    # Stage 3: Risk assessment (uses both above)
    risks = call_text_agent(
        system_prompt="Assess risks for this workout",
        user_prompt=f"...",
        response_model=RiskAssessment,
        temperature=0.1,
        max_output_tokens=600,
    )
    
    # Merge results back into single reasoning_plan for downstream nodes
    reasoning_plan = merge_stages(classification, layout, risks)
    return {"reasoning_plan": reasoning_plan}
```

**Phase 1C: Update State & Graph (1 day)**

Changes to state.py:
```python
# Add fields for intermediate results
class PosterState(TypedDict, total=False):
    reasoning_plan: dict[str, Any]
    # NEW: Optional intermediate fields (for tracing)
    reasoning_classification: dict[str, Any]
    reasoning_layout: dict[str, Any]
    reasoning_risks: dict[str, Any]
```

Changes to graph.py:
```python
# Tracing now captures all 3 stages
trace["reasoning_stages"] = {
    "classification": result1.payload,
    "layout": result2.payload,
    "risks": result3.payload,
}
```

**Phase 1D: Testing (2-3 days)**

New test file: `tests/test_langgraph_tier1.py`
```python
def test_reasoning_classification_schema_valid():
    """Verify classification schema parses correctly"""
    # Mock Gemini to return valid classification JSON
    # Assert no fallback to heuristics
    
def test_reasoning_staged_pipeline():
    """Test 3-stage reasoning with real Gemini API"""
    # Run with LANGGRAPH_TESTING_TIER=1
    # Assert all 3 stages succeed
    # Assert similarity_score > 0.95
    
def test_designer_receives_merged_reasoning():
    """Verify downstream nodes get merged result"""
    # Assert designer_node receives complete reasoning_plan
    # Assert backward compatibility
```

### Expected Results

**Before (Monolithic):**
- LLM success rate: 20%
- Fallback rate: 80%
- Token cost: ~1200 per run

**After (Staged):**
- LLM success rate: 85%+
- Fallback rate: 15%
- Token cost: ~1800 per run (+50%)
- Total accuracy: 75% → 88%

### Files Modified
| File | Changes | Lines |
|------|---------|-------|
| llm_schemas.py | Add 3 new schemas, remove monolithic | +80, -50 |
| nodes.py | Replace reasoning_node with staged | +100, -80 |
| state.py | Add intermediate fields | +5 |
| graph.py | Tracing for 3 stages | +20 |
| tests/ | New tier 1 tests | +150 |
| **Total** | | **+255 lines** |

### Dependencies
- None (pure refactoring of existing LLM calls)
- No new libraries needed
- Backward compatible with existing state format

### Risks
- **Medium**: If Gemini still fails on risk flags schema, staged approach doesn't help
- **Mitigation**: Add fallback HTML markup parsing (accept HTML response, extract JSON-like content)

---

# TIER 2: Improve Quality Thresholds

## Goal
Increase validation pass rate from 20% → 50%+ (reduce false passes from critic)

## Strategy
Strengthen critic node and validator node to catch quality issues earlier.

### Problem Analysis

**Current Situation:**
```
Designer Node → Mediocre Prompt
  ↓
Critic Node → score=70 → pass=True (too lenient!)
  ↓
Generator → Creates image
  ↓
Validator → Catches corruption (too late)
```

**Issue:** Critic doesn't have enough power to reject bad prompts. Score=70 should be a WARNING, not a PASS.

### Implementation Plan

**Phase 2A: Strengthen Critic Validation (2-3 days)**

Update CriticReviewModel in llm_schemas.py:
```python
class CriticReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    pass_: bool = Field(alias="pass")
    score_0_to_100: int = Field(ge=0, le=100)
    
    # NEW: Mandatory blocker detection
    critical_blockers: list[str] = Field(default_factory=list)  # Must be empty to pass
    
    # NEW: Explicit hallucination risk scoring
    hallucination_risk: HallucinationRisk
    
    # NEW: Compliance requirements
    compliance_failures: list[str] = Field(default_factory=list)
    
    confidence: float = Field(ge=0.0, le=1.0)
```

Update critic_node in nodes.py:
```python
def critic_node(state: PosterState) -> PosterState:
    # ... existing code ...
    
    review = call_text_agent(...)
    
    # NEW: Hard enforcement logic
    is_valid = (
        review.score_0_to_100 >= 85  # Raise threshold from 70
        and len(review.critical_blockers) == 0  # No blockers allowed
        and review.hallucination_risk.added_content_risk == "low"  # No added content
        and review.compliance_failures == []  # All compliance checks pass
    )
    
    if not is_valid:
        # NEW: Detailed feedback for retry
        state["feedback"] = {
            "score": review.score_0_to_100,
            "blockers": review.critical_blockers,
            "risks": review.hallucination_risk.model_dump(),
            "compliance": review.compliance_failures,
        }
        # Route back to designer (not reasoning) for refinement
        return route_to_designer_refinement(state)
    
    return {"final_graphic_prompt": candidate_prompt, ...}
```

**Phase 2B: Add Designer Refinement Loop (2 days)**

New function in nodes.py:
```python
def designer_refinement_node(state: PosterState) -> PosterState:
    """
    Refactor prompt based on critic feedback.
    Lighter-weight than full reasoning loop.
    """
    candidate_prompt = state.get("candidate_graphic_prompt", "")
    feedback = state.get("feedback", {})
    
    system_prompt = (
        "You are DesignerAgent refining a prompt. "
        "Address these critic concerns: " + str(feedback)
    )
    user_prompt = (
        f"CURRENT_PROMPT:\n{candidate_prompt}\n\n"
        f"FEEDBACK:\n{feedback}\n\n"
        "Refine the prompt to address concerns."
    )
    
    refined = call_text_agent(
        model=state["designer_model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_model=DesignerRefinementSchema,  # ← Smaller schema
        max_output_tokens=1000,
    )
    
    return {"candidate_graphic_prompt": refined}
```

Add to graph.py routing:
```python
def should_refine_design(state: PosterState) -> str:
    """Route to refinement if critic found issues but fixable"""
    feedback = state.get("feedback", {})
    score = feedback.get("score", 0)
    
    if score >= 70 and score < 85:
        return "designer_refinement"  # ← New node
    elif score < 70:
        return "reasoning"  # ← Back to reasoning
    else:
        return "generator"  # ← Proceed

workflow.add_node("designer_refinement", designer_refinement_node)
workflow.add_edge("critic", should_refine_design)
workflow.add_edge("designer_refinement", "critic")  # ← Feedback loop
```

**Phase 2C: Improve Validator Thresholds (2 days)**

Update validation_node in nodes.py:
```python
def validation_node(state: PosterState) -> PosterState:
    # NEW: Three-tier similarity scoring
    extracted_text = extract_text_from_image(image_path)
    canonical = state.get("canonical_rows", [])
    
    similarity = compute_similarity(extracted_text, canonical)
    
    # TIER 1: High confidence pass (no retry)
    if similarity >= 0.95:
        return {
            "is_valid": True,
            "validation_passed": True,
            "similarity_score": similarity,
        }
    
    # TIER 2: Medium confidence - needs semantic validation
    if similarity >= 0.85:
        semantic_check = semantic_validate(extracted_text, canonical)
        if semantic_check["all_movements_present"]:
            return {"is_valid": True, ...}
        else:
            # Semantic check failed - route to critic, not reasoning
            return route_to_critic_review(state)
    
    # TIER 3: Low confidence - needs retry
    if similarity < 0.85 and state["retry_count"] < state["max_retries"]:
        return {"is_valid": False, "retry_requested": True, ...}
    else:
        return {"is_valid": False, "error": "Max retries exceeded"}
```

Add semantic validation helper:
```python
def semantic_validate(extracted_text: str, canonical_rows: list) -> dict:
    """Check if movements are semantically correct, not just string match"""
    movements_expected = {row["name"] for row in canonical_rows}
    movements_extracted = extract_movement_names(extracted_text)
    
    return {
        "all_movements_present": movements_expected <= movements_extracted,
        "movement_names_correct": movements_expected == movements_extracted,
        "weights_in_range": check_weights_in_range(extracted_text),
        "sections_grouped": check_section_grouping(extracted_text),
        "format_correct": check_format(extracted_text),
    }
```

**Phase 2D: Testing & Validation (2 days)**

New tests in tests/test_langgraph_tier2.py:
```python
def test_critic_score_85_threshold():
    """Verify score < 85 triggers refinement, not pass"""
    
def test_semantic_validation_catches_garbled_weights():
    """Verify "Womsn 55 Ibs" detected as invalid"""
    
def test_designer_refinement_improves_score():
    """Verify refinement loop increases critic score"""
    
def test_similarity_tier_routing():
    """Verify 0.85-0.95 similarity routes to semantic validation"""
```

### Expected Results

**Before:**
- Critic false-positive rate: 100% (all pass)
- Validation catch rate: 100% (always needed)
- Critic score distribution: 0-70 (useless)

**After:**
- Critic false-positive rate: 20% (catches issues early)
- Validation catch rate: 50% (half caught by critic)
- Critic score distribution: 70-100 (meaningful)
- Total accuracy: 88% → 91%

### Files Modified
| File | Changes | Lines |
|------|---------|-------|
| llm_schemas.py | Add fields to CriticReviewModel | +30 |
| nodes.py | Designer refinement + semantic validation | +150 |
| graph.py | Add refinement node, update routing | +40 |
| tests/ | New tier 2 tests | +120 |
| **Total** | | **+340 lines** |

### Dependencies
- NLP library for movement name extraction (spaCy or simple regex)
- Optional: Fuzzy matching library (already have fuzzywuzzy)

### Risks
- **Medium**: Refinement loop could get stuck (reject → refine → reject)
- **Mitigation**: Add max refinement attempts (3), then escalate to reasoning

---

# TIER 3: Architectural Redesign (Hybrid Model)

## Goal
Reduce prompt complexity → increase accuracy from 91% → 94%

## Strategy
**Deterministic parsing first, then simpler LLM prompts.**

### Problem Analysis

**Current Bottleneck:**
```
Raw WOD (complex structure)
  ↓
Reasoning LLM (receives raw data, must interpret structure)
  → JSON fails (too much interpretation needed)
  ↓
Designer LLM (receives fuzzy reasoning output)
  → Inherits errors from reasoning failure
```

**Issue:** LLM is doing too much (parsing + reasoning + design). Split into deterministic + LLM.

### Implementation Plan

**Phase 3A: Deterministic Workout Parser (3-4 days)**

New file: theassembly/langgraph_pipeline/parser.py (~250 lines)

```python
class WorkoutParser:
    """Deterministically extract structured data from raw WOD"""
    
    def parse(self, raw_wod: dict) -> ParsedWorkout:
        """
        Extract:
        - Movements (with exact names, reps, weights)
        - Structure (EMOM? AMRAP? For time?)
        - Finisher (if exists)
        - Technical cues
        
        Return structured object, no LLM interpretation.
        """
        stimulus = raw_wod.get("stimulus", "")
        movements = raw_wod.get("movements", [])
        content = raw_wod.get("content", "")
        
        # Deterministic extraction
        parsed = ParsedWorkout(
            workout_type=self._extract_type(stimulus, content),
            time_cap=self._extract_time_cap(stimulus, content),
            movements=self._extract_movements(movements),
            finisher=self._extract_finisher(movements),
            scoring=self._extract_scoring(content),
            scaling_options=self._extract_scaling(movements),
        )
        
        return parsed

@dataclass
class ParsedWorkout:
    workout_type: Literal["amrap", "emom", "for_time", "strength", "team"]
    time_cap: Optional[timedelta]
    movements: list[ParsedMovement]
    finisher: Optional[ParsedFinisher]
    scoring: str
    scaling_options: list[ScalingOption]

@dataclass
class ParsedMovement:
    name: str
    reps: str
    rx_weight: str
    scaled_weight: str
    section: str
    order: int
```

**Phase 3B: Simplified Reasoning LLM (2 days)**

Update reasoning_node to use parsed data:
```python
def reasoning_node(state: PosterState) -> PosterState:
    raw_wod = state.get("raw_wod", {})
    
    # NEW: Deterministic parsing first
    parsed_workout = WorkoutParser().parse(raw_wod)
    state["parsed_workout"] = parsed_workout.model_dump()
    
    # Now LLM gets simpler input: structured data
    system_prompt = (
        "You are ReasoningAgent. Receive structured workout data. "
        "Return layout and visual strategy (simple JSON)."
    )
    
    user_prompt = (
        f"WORKOUT_TYPE: {parsed_workout.workout_type}\n"
        f"MOVEMENTS_COUNT: {len(parsed_workout.movements)}\n"
        f"HAS_FINISHER: {parsed_workout.finisher is not None}\n"
        f"TIME_CAP: {parsed_workout.time_cap}\n"
        "Suggest layout strategy and visual approach."
    )
    
    # Use SIMPLIFIED schema (not monolithic)
    plan = call_text_agent(
        response_model=SimpleReasoningSchema,  # ← Much smaller
        user_prompt=user_prompt,
        max_output_tokens=400,  # ← Fewer tokens
    )
    
    return {
        "parsed_workout": parsed_workout,
        "reasoning_plan": plan,
    }
```

New simplified schema in llm_schemas.py:
```python
class SimpleReasoningSchema(BaseModel):
    """Much simpler than ReasoningPlanModel"""
    layout_type: Literal["vertical", "horizontal", "grid", "split"]
    visual_style: Literal["dark", "light", "high_contrast"]
    focus_areas: list[str]  # ["typography", "spacing", "colors"]
    rationale: str
```

**Phase 3C: Designer with Parsed Context (3-4 days)**

Update designer_node:
```python
def designer_node(state: PosterState) -> PosterState:
    parsed = state.get("parsed_workout")
    reasoning = state.get("reasoning_plan")
    
    # Build structured context for designer
    movements_str = format_movements_for_design(parsed.movements)
    
    system_prompt = (
        "You are DesignAgent. Create a workout poster structure. "
        "Preserve exact movement data. Return simple JSON."
    )
    
    user_prompt = (
        f"WORKOUT: {parsed.workout_type}\n"
        f"MOVEMENTS:\n{movements_str}\n"
        f"LAYOUT: {reasoning.layout_type}\n"
        f"STYLE: {reasoning.visual_style}\n"
        "Design the poster layout and styling."
    )
    
    # Simpler schema again
    design = call_text_agent(
        response_model=SimpleDesignSchema,  # ← Much simpler
        user_prompt=user_prompt,
        max_output_tokens=800,
    )
    
    # No risk of hallucinating movements since they're pre-extracted
    final_prompt = build_image_prompt_from_design(design, parsed)
    
    return {
        "candidate_graphic_prompt": final_prompt,
        "designer_draft": design,
    }
```

New simplified schema:
```python
class SimpleDesignSchema(BaseModel):
    """Simple design output"""
    layout_structure: str  # "Title | Main Movements | Finisher | Footer"
    color_scheme: str  # "dark with blue accents"
    typography_style: str  # "bold sans-serif"
    emphasis_areas: list[str]  # ["movement names", "weights", "time cap"]
```

**Phase 3D: Graph Refinement (1 day)**

Update graph.py:
```python
def _compile_graph():
    workflow = StateGraph(PosterState)
    
    # Node order with parsed data flowing through
    workflow.add_node("parser", parser_node)  # ← NEW: Deterministic
    workflow.add_node("reasoning", reasoning_node)
    workflow.add_node("editor", editor_node)
    workflow.add_node("architect", architect_node)
    workflow.add_node("designer", designer_node)
    workflow.add_node("critic", critic_node)
    workflow.add_node("generator", generator_node)
    workflow.add_node("validator", validation_node)
    
    workflow.set_entry_point("parser")  # ← Start with deterministic parsing
    workflow.add_edge("parser", "reasoning")
    # ... rest of edges
```

**Phase 3E: Testing Hybrid Model (2-3 days)**

New tests in tests/test_langgraph_tier3.py:
```python
def test_deterministic_parser_extracts_movements():
    """Verify parser extracts exact movement data"""
    
def test_simplified_reasoning_schema_parses():
    """Verify simple schema has high JSON success rate"""
    
def test_designer_receives_parsed_movements():
    """Verify designer can't hallucinate movements"""
    
def test_hybrid_accuracy_94_percent():
    """Integration test: verify accuracy improvement to 94%"""
```

### Expected Results

**Before (Monolithic):**
- Reasoning LLM complexity: High (parse + reason)
- JSON failure points: 2 (reasoning, designer)
- Accuracy: 91%

**After (Hybrid):**
- Reasoning LLM complexity: Low (just recommend)
- JSON failure points: 1 (only designer, reasoning is deterministic)
- Accuracy: 94%
- Cost increase: +20% (additional parser call)

### Files Modified
| File | Changes | Lines |
|------|---------|-------|
| parser.py | NEW file | +250 |
| llm_schemas.py | Add SimpleReasoningSchema, SimpleDesignSchema | +50 |
| nodes.py | Add parser_node, update reasoning/designer | +200 |
| graph.py | Add parser node to graph | +30 |
| state.py | Add parsed_workout field | +5 |
| tests/ | New tier 3 tests | +180 |
| **Total** | | **+715 lines** |

### Dependencies
- None (pure logic + existing libraries)

### Risks
- **Medium**: If parser misses edge cases, LLM can't compensate
- **Mitigation**: Comprehensive parser tests, fallback to raw data if parsing fails

---

# TIER 4: Professional-Grade Multi-Expert Ensemble

## Goal
Reach 98%+ accuracy with multi-model consensus and human feedback loop.

## Strategy
Use multiple specialized models + human refinement for high-value cases.

### Architecture

```
Raw WOD
  ↓
Deterministic Parser
  ├────→ Claude 3.5 (Planning expertise)
  │        └→ Workout intent, visual metaphor
  │
  ├────→ Gemini 2.5 (Image generation expertise)
  │        └→ Visual prototype, style
  │
  └────→ Llama 3.1 (Movement expertise)
           └→ Movement validation, scaling

         ↓ Orchestrate
    
    Multi-Expert Consensus
         ↓
    Generate Prompt v1
         ↓
    Quality Score < 85?
         ↓
    Human Review (Coach)
         ↓
    Collect Feedback (2-3 clicks)
         ↓
    Fine-tune Models (batch daily)
         ↓
    Upload Improved Model
         ↓
    Retry with Updated Model
```

### Implementation Plan

**Phase 4A: Multi-LLM Abstraction Layer (3 days)**

New file: theassembly/langgraph_pipeline/multi_agent.py (~300 lines)

```python
class MultiAgentOrchestrator:
    """Coordinate multiple LLM experts"""
    
    async def get_expert_opinions(self, parsed_workout: ParsedWorkout):
        """Get recommendations from all experts in parallel"""
        
        # Claude: Planning
        claude_plan = await self.claude_planning_agent(parsed_workout)
        
        # Gemini: Visual
        gemini_visual = await self.gemini_visual_agent(parsed_workout)
        
        # Llama: Movement
        llama_validation = await self.llama_movement_agent(parsed_workout)
        
        return MultiAgentResult(
            planning=claude_plan,
            visual=gemini_visual,
            validation=llama_validation,
        )
    
    def synthesize_consensus(self, opinions: MultiAgentResult) -> str:
        """Merge expert opinions into single final prompt"""
        # Weighted voting / expert consensus
        final_prompt = orchestrate(
            planning=opinions.planning,
            visual=opinions.visual,
            validation=opinions.validation,
        )
        return final_prompt
```

**Phase 4B: Human Feedback Collection (4-5 days)**

New file: theassembly/langgraph_pipeline/human_loop.py (~200 lines)

```python
class HumanFeedbackCollector:
    """Gather coach feedback on generated images"""
    
    def should_review(self, critic_score: int) -> bool:
        """Determine if image needs human review"""
        return 70 <= critic_score < 90
    
    def create_review_task(self, image_path: str, date: str) -> ReviewTask:
        """Create task for human coach to review"""
        return ReviewTask(
            image_id=date,
            image_path=image_path,
            questions=[
                "Movement rendering accurate? [Yes/No]",
                "Weights visible and correct? [Yes/No]",
                "Layout professional? [Yes/No]",
                "Typography clear? [Yes/No]",
                "Any hallucinations? [Describe]",
            ],
            quick_actions=[
                "Approve (publish)",
                "Minor fixes",
                "Major redesign",
                "Reject (use backup)",
            ],
        )
    
    def process_feedback(self, feedback: ReviewFeedback):
        """Store feedback for fine-tuning"""
        store_to_training_database({
            "image_id": feedback.image_id,
            "critic_score": feedback.critic_score,
            "human_score": feedback.human_score,
            "issues": feedback.issues,
            "approved": feedback.approved,
            "timestamp": datetime.now(),
        })
```

**Phase 4C: Daily Fine-Tuning Pipeline (3-4 days)**

New file: theassembly/langgraph_pipeline/fine_tuning.py (~250 lines)

```python
class FineTuningManager:
    """Update models based on collected feedback"""
    
    async def daily_batch_update(self):
        """Run once per day to improve models"""
        
        # Collect feedback from last 24h
        feedback_samples = fetch_feedback_last_24h()
        
        if len(feedback_samples) < 10:
            return  # Need minimum samples
        
        # Separate into success/failure cases
        successes = [s for s in feedback_samples if s.approved]
        failures = [s for s in feedback_samples if not s.approved]
        
        # Update designer model with successful prompts
        await self.update_designer_model(successes, failures)
        
        # Upload new model version
        await self.upload_model_version()
        
        # Update graph to use new model
        update_state_with_new_model_id()
```

**Phase 4D: Fallback & Safety (2-3 days)**

```python
class SafetyManager:
    """Ensure no bad images published"""
    
    def multi_stage_validation(self, image_path: str) -> ValidationResult:
        """Run multiple validation checks"""
        
        # Stage 1: OCR similarity
        ocr_score = validate_ocr(image_path)
        
        # Stage 2: Semantic structure
        semantic_valid = validate_structure(image_path)
        
        # Stage 3: Movement detection (vision model)
        movements_detected = detect_movements(image_path)
        
        # Stage 4: Human eye (if score 70-90)
        if 0.70 <= ocr_score < 0.95:
            human_review = wait_for_human_review(image_path)
            return human_review
        
        # Stage 5: Automatic decision
        if ocr_score >= 0.95 and semantic_valid and len(movements_detected) > 0:
            return ValidationResult(approved=True, reason="All checks passed")
        else:
            return ValidationResult(approved=False, reason="Failed validation")
```

**Phase 4E: Integration & Testing (3-4 days)**

Update graph.py:
```python
def _compile_graph():
    # ... existing nodes ...
    
    workflow.add_node("multi_agent", multi_agent_node)
    workflow.add_node("human_feedback", human_feedback_node)
    workflow.add_node("safety_check", safety_check_node)
    
    workflow.add_edge("parser", "multi_agent")
    workflow.add_edge("multi_agent", "designer")
    workflow.add_edge("validator", "safety_check")
    
    # Conditional edge: human review for borderline cases
    workflow.add_conditional_edges(
        "safety_check",
        lambda state: "human_feedback" if state.get("needs_review") else "end",
        {"human_feedback": "end", "end": END},
    )
```

New comprehensive tests:
```python
def test_multi_agent_consensus():
    """Verify all 3 experts consulted"""
    
def test_human_feedback_collection():
    """Verify feedback persisted for fine-tuning"""
    
def test_daily_fine_tuning_updates():
    """Verify models improve with feedback"""
    
def test_safety_validation_catches_edge_cases():
    """Verify 4-stage validation"""
    
def test_end_to_end_professional_quality():
    """Integration test: 98%+ accuracy"""
```

### Expected Results

**Before:**
- Single model
- No feedback loop
- Accuracy: 94%
- Cost: $0.10 per poster

**After:**
- 3-model ensemble
- Daily fine-tuning
- Accuracy: 98%+
- Cost: $0.30 per poster
- Human review rate: 10-20% (only borderline cases)

### Files Modified
| File | Changes | Lines |
|------|---------|-------|
| multi_agent.py | NEW file | +300 |
| human_loop.py | NEW file | +200 |
| fine_tuning.py | NEW file | +250 |
| orchestrator.py | NEW file | +150 |
| graph.py | Add multi-agent + feedback nodes | +60 |
| nodes.py | Update designer with consensus | +100 |
| tests/ | Comprehensive tier 4 tests | +300 |
| **Total** | | **+1,360 lines** |

### Dependencies
- Claude API (anthropic SDK)
- Llama API (via Replicate or local)
- Async library (already using asyncio)
- Database for feedback storage (SQLite or PostgreSQL)
- Model hosting (Hugging Face Model Hub or custom)

### Risks
- **High**: Multi-model coordination complexity
- **High**: Fine-tuning pipeline failures could degrade quality
- **High**: Human review process can become bottleneck
- **Mitigations:**
  - Comprehensive testing of orchestration
  - Staged rollout of fine-tuned models
  - Human review queue management + SLA

---

## Summary: Implementation Effort by Tier

| Tier | Effort | Schedule | Team | Dependencies |
|------|--------|----------|------|---|
| **Tier 1** | Medium | 1-2 weeks | 1 engineer | Gemini API (existing) |
| **Tier 2** | Medium | 2-3 weeks | 1 engineer | Spacy/regex |
| **Tier 3** | High | 4-6 weeks | 2 engineers | None new |
| **Tier 4** | Very High | 8-12 weeks | 3-4 engineers | Claude, Llama, DB |

## ROI Analysis

**Tier 1 → 2 (Budget: ~$2K, Timeline: 3 weeks)**
- Cost per image: $0.01 → $0.015 (+50%)
- Accuracy: 75% → 88%
- Best for: Teams with time constraints
- ROI: High (quick win)

**Tier 1 → 3 (Budget: ~$8K, Timeline: 6 weeks)**
- Cost per image: $0.01 → $0.015
- Accuracy: 75% → 94%
- Best for: Production systems
- ROI: Medium-High (professional quality possible)

**Tier 1 → 4 (Budget: ~$20K+, Timeline: 12 weeks)**
- Cost per image: $0.01 → $0.30
- Accuracy: 75% → 98%+
- Best for: Enterprise/mission-critical
- ROI: Low (human labor becomes dominant cost)

## Recommendation

**For your portfolio:** Implement Tier 1 + 2 (3 weeks)
- Shows you understand root causes
- Demonstrates problem-solving
- Professional quality not needed for demo
- Cost-benefit justified

**For production:** Plan for Tier 3 (6 weeks)
- Hybrid model is sweet spot
- 94% accuracy professional-grade
- Cost reasonable ($0.015/image)
- No human bottleneck

**For enterprise:** Consider Tier 4 after validating Tier 3
- Wait for user feedback
- Implement fine-tuning loop gradually
- Human review becomes optional later


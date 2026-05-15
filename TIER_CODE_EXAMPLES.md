# Code Examples: Tier-by-Tier Implementation

## TIER 1: Schema Decomposition

### Before (Current - Monolithic)
```python
# llm_schemas.py - CURRENT
class ReasoningPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workout_archetype: Literal["amrap", "emom", "for_time", "strength", "team", "mixed"]
    intensity_profile: Literal["low", "moderate", "high", "mixed"]
    layout_strategy: Literal["vertical_stack", "masonry_2col", "split_pane"]
    finisher_strategy: Literal["none", "right_sidebar", "segmented_sidebar"]
    visual_goal: str = Field(min_length=10, max_length=200)
    section_priority: list[Literal["header", "main_movements", "finisher", "footer"]]
    risk_flags: list[RiskFlag] = Field(default_factory=list)  # ← Complex nested
    retry_directives: list[str] = Field(default_factory=list)
    non_negotiables: list[str] = Field(min_length=4)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=20, max_length=500)
    # JSON serialization often fails here ↑
```

```python
# nodes.py - CURRENT (single call fails 80% of the time)
def reasoning_node(state: PosterState) -> PosterState:
    raw = state.get("raw_wod", {})
    
    system_prompt = "You are ReasoningAgent..."
    user_prompt = f"WORKOUT_JSON:\n{raw}\n..."
    
    # Single LLM call with complex schema
    plan: dict[str, Any] = {}
    if state.get("api_key"):
        try:
            result = call_text_agent(
                response_model=ReasoningPlanModel,  # ← Large schema
                user_prompt=user_prompt,
                max_output_tokens=1200,  # ← Lots of tokens needed
            )
            plan = result.payload
        except TextAgentError as exc:
            # Fails ~80% of the time
            plan = _heuristic_reasoning(raw, "")
            
    return {"reasoning_plan": plan}
```

### After (Tier 1 - Decomposed)

```python
# llm_schemas.py - TIER 1 (3 simpler schemas)
class WorkoutClassification(BaseModel):
    """Stage 1: Just classify the workout"""
    workout_archetype: Literal["amrap", "emom", "for_time", "strength", "team", "mixed"]
    intensity_profile: Literal["low", "moderate", "high", "mixed"]
    confidence: float = Field(ge=0.0, le=1.0)

class LayoutRecommendation(BaseModel):
    """Stage 2: Recommend layout based on classification"""
    layout_strategy: Literal["vertical_stack", "masonry_2col", "split_pane"]
    finisher_strategy: Literal["none", "right_sidebar", "segmented_sidebar"]
    visual_goal: str = Field(min_length=10, max_length=200)
    rationale: str = Field(min_length=20, max_length=500)

class RiskAssessment(BaseModel):
    """Stage 3: Assess risks (can fail gracefully)"""
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    non_negotiables: list[str] = Field(default_factory=list)
    section_priority: list[str] = Field(default_factory=list)
```

```python
# nodes.py - TIER 1 (3 simpler calls, better success rate)
def reasoning_node(state: PosterState) -> PosterState:
    raw = state.get("raw_wod", {})
    
    # Stage 1: Classification (high success - 2 fields)
    classification = call_text_agent(
        system_prompt="Classify: what type of workout is this?",
        user_prompt=f"Workout: {raw.get('stimulus')}",
        response_model=WorkoutClassification,
        max_output_tokens=200,  # ← Fewer tokens
    )
    
    # Stage 2: Layout (medium success - 3 fields)
    layout = call_text_agent(
        system_prompt="Given this classification, recommend layout",
        user_prompt=f"Type: {classification.workout_archetype}",
        response_model=LayoutRecommendation,
        max_output_tokens=300,
    )
    
    # Stage 3: Risk Assessment (can fail, has fallback)
    try:
        risks = call_text_agent(
            system_prompt="Assess risks",
            user_prompt=f"...",
            response_model=RiskAssessment,
            max_output_tokens=600,
        )
    except TextAgentError:
        risks = {"risk_flags": [], "non_negotiables": []}
    
    # Merge stages back together
    reasoning_plan = {
        "workout_archetype": classification.workout_archetype,
        "intensity_profile": classification.intensity_profile,
        "layout_strategy": layout.layout_strategy,
        "finisher_strategy": layout.finisher_strategy,
        "visual_goal": layout.visual_goal,
        "risk_flags": risks.get("risk_flags", []),
        # ... etc
    }
    
    return {"reasoning_plan": reasoning_plan}
```

**Expected Results:**
- Stage 1: 95% success (simple binary)
- Stage 2: 90% success (3 choices)
- Stage 3: 70% success (complex, but failure is acceptable)
- **Overall: 95% * 90% * 70% = 60% strict, but with fallbacks → ~90% effective**

---

## TIER 2: Critic Strengthening

### Before (Current - Too Lenient)
```python
# nodes.py - CURRENT
def critic_node(state: PosterState) -> PosterState:
    candidate_prompt = state.get("candidate_graphic_prompt", "")
    
    result = call_text_agent(
        response_model=CriticReviewModel,
        user_prompt=f"PROMPT:\n{candidate_prompt}",
    )
    review = result.payload
    
    # TOO LENIENT: score=70 → pass=True
    is_valid = review.get("pass", False)  # Only checks "pass" field
    
    if is_valid:
        return {"final_graphic_prompt": candidate_prompt}
    else:
        state["retry_requested"] = True
        return state
```

### After (Tier 2 - Strict Quality Gates)

```python
# llm_schemas.py - TIER 2 (enhanced CriticReviewModel)
class CriticReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    pass_: bool = Field(alias="pass")
    score_0_to_100: int = Field(ge=0, le=100)
    
    # NEW: Mandatory blocker detection
    critical_blockers: list[str] = Field(
        default_factory=list,
        description="Critical issues that prevent publication"
    )
    
    # NEW: Explicit hallucination risk
    hallucination_risk: HallucinationRisk
    
    # NEW: Compliance tracking
    compliance_failures: list[str] = Field(
        default_factory=list,
        description="Violated compliance requirements"
    )
    
    confidence: float = Field(ge=0.0, le=1.0)

# nodes.py - NEW: Designer Refinement Node
def designer_refinement_node(state: PosterState) -> PosterState:
    """Refactor prompt based on critic feedback (lighter weight)"""
    candidate_prompt = state.get("candidate_graphic_prompt", "")
    feedback = state.get("feedback", {})
    
    system_prompt = (
        "You are DesignerAgent refining a prompt. "
        "The critic found these issues: " + str(feedback) +
        "\nRefine the prompt to address them."
    )
    
    user_prompt = (
        f"CURRENT_PROMPT:\n{candidate_prompt}\n\n"
        f"ISSUES TO FIX:\n{feedback}\n\n"
        "Provide a refined prompt that addresses these concerns."
    )
    
    # NEW: Simpler schema for refinement
    refined = call_text_agent(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_model=DesignerRefinementSchema,  # Simpler than full design
        max_output_tokens=800,
    )
    
    return {"candidate_graphic_prompt": refined}

# nodes.py - TIER 2 (strict routing logic)
def critic_node(state: PosterState) -> PosterState:
    candidate_prompt = state.get("candidate_graphic_prompt", "")
    
    review = call_text_agent(
        response_model=CriticReviewModel,
        user_prompt=f"PROMPT:\n{candidate_prompt}",
    )
    
    # NEW: Hard enforcement
    is_valid = (
        review.score_0_to_100 >= 85 and  # Raise threshold from 70!
        len(review.critical_blockers) == 0 and
        review.hallucination_risk.added_content_risk == "low" and
        len(review.compliance_failures) == 0
    )
    
    if is_valid:
        return {"final_graphic_prompt": candidate_prompt}
    
    # NEW: Route to refinement instead of retry
    score = review.score_0_to_100
    if score >= 70:
        # Salvageable - refine instead of restart
        state["feedback"] = {
            "score": score,
            "blockers": review.critical_blockers,
            "risks": review.hallucination_risk.model_dump(),
        }
        return {"needs_refinement": True}
    else:
        # Restart reasoning
        state["feedback"] = "Critic score too low, restarting reasoning"
        return state

# graph.py - TIER 2 (new routing)
def route_after_critic(state: PosterState) -> str:
    if state.get("needs_refinement"):
        return "designer_refinement"
    elif state.get("retry_requested"):
        return "reasoning"
    else:
        return "generator"

workflow.add_node("designer_refinement", designer_refinement_node)
workflow.add_conditional_edges("critic", route_after_critic, {...})
```

**Expected Behavior:**
```
Critic score: 70 → "Needs refinement" → Designer refines → Critic re-checks (score: 88)
Critic score: 55 → "Too low" → Back to reasoning (retry)
Critic score: 90+ → "Approved" → Proceed to generator
```

---

## TIER 3: Hybrid Deterministic + LLM

### Before (Current - LLM Does Everything)
```python
# Raw WOD → reasoning LLM → design → image
# LLM must parse and interpret structure
```

### After (Tier 3 - Deterministic First)

```python
# NEW: parser.py - Deterministic extraction
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

@dataclass
class ParsedMovement:
    name: str
    reps: str
    rx_weight: str
    scaled_weight: str
    section: str
    order: int

@dataclass
class ParsedWorkout:
    workout_type: str  # "amrap", "emom", "for_time", etc.
    time_cap: Optional[timedelta]
    movements: list[ParsedMovement]
    finisher: Optional[dict]
    scoring: str
    scaling_options: list[dict]

class WorkoutParser:
    def parse(self, raw_wod: dict) -> ParsedWorkout:
        """Deterministically extract structure (no LLM guessing)"""
        
        stimulus = raw_wod.get("stimulus", "")
        movements = raw_wod.get("movements", [])
        
        # Extract type (deterministic)
        workout_type = self._detect_type(stimulus)
        
        # Extract time cap (deterministic)
        time_cap = self._extract_time_cap(stimulus)
        
        # Extract movements (deterministic)
        parsed_movements = [
            ParsedMovement(
                name=m.get("name", ""),
                reps=m.get("reps", ""),
                rx_weight=m.get("rx_weight", ""),
                scaled_weight=m.get("scaled_weight", ""),
                section=m.get("section", ""),
                order=i,
            )
            for i, m in enumerate(movements)
        ]
        
        # Separate finisher (deterministic)
        finisher_movements = [m for m in parsed_movements if m.section == "Finisher"]
        
        return ParsedWorkout(
            workout_type=workout_type,
            time_cap=time_cap,
            movements=parsed_movements,
            finisher=finisher_movements if finisher_movements else None,
            scoring=self._extract_scoring(stimulus),
            scaling_options=self._extract_scaling_options(movements),
        )
    
    def _detect_type(self, stimulus: str) -> str:
        """Deterministic pattern matching"""
        s_lower = stimulus.lower()
        if "amrap" in s_lower or "as many reps" in s_lower:
            return "amrap"
        elif "emom" in s_lower or "every minute on the minute" in s_lower:
            return "emom"
        elif "for time" in s_lower or "as fast as possible" in s_lower:
            return "for_time"
        else:
            return "mixed"
    
    # Similar methods for time cap, scaling, etc.

# nodes.py - NEW: Parser node
def parser_node(state: PosterState) -> PosterState:
    raw_wod = state.get("raw_wod", {})
    
    parsed = WorkoutParser().parse(raw_wod)
    
    return {
        "parsed_workout": parsed.model_dump(),  # Add to state
        # Pass through remaining state
    }

# nodes.py - UPDATED: Simpler reasoning (uses parsed data)
class SimpleReasoningSchema(BaseModel):
    """Simpler schema - just layout and style"""
    layout_type: Literal["vertical", "horizontal", "grid", "split"]
    visual_style: Literal["dark", "light", "high_contrast"]
    focus_areas: list[str]
    rationale: str

def reasoning_node(state: PosterState) -> PosterState:
    parsed = state.get("parsed_workout", {})
    
    system_prompt = (
        "Given this structured workout data, suggest layout and visual approach. "
        "Return simple JSON."
    )
    
    user_prompt = (
        f"WORKOUT_TYPE: {parsed.get('workout_type')}\n"
        f"MOVEMENTS_COUNT: {len(parsed.get('movements', []))}\n"
        f"HAS_FINISHER: {parsed.get('finisher') is not None}\n"
        f"TIME_CAP: {parsed.get('time_cap')}\n"
        "Suggest visual approach."
    )
    
    # Simpler schema with fewer fields
    plan = call_text_agent(
        response_model=SimpleReasoningSchema,
        user_prompt=user_prompt,
        max_output_tokens=400,  # ← Fewer tokens needed
    )
    
    return {"reasoning_plan": plan}

# graph.py - TIER 3 (add parser at start)
def _compile_graph():
    workflow = StateGraph(PosterState)
    
    # Entry point: Parse first
    workflow.set_entry_point("parser")
    workflow.add_edge("parser", "reasoning")
    workflow.add_edge("reasoning", "editor")
    # ... rest of pipeline
```

**Key Benefit:**
```
Before (LLM does parsing):
  Raw WOD → Reasoning LLM → Interprets structure (error-prone)
  
After (Deterministic parsing):
  Raw WOD → Parser → Structured data → Simpler Reasoning LLM (confident)
  
Movement hallucination eliminated: Parser extracts exact names/weights
```

---

## TIER 4: Multi-Expert Ensemble

### New Multi-Agent Orchestration

```python
# NEW: multi_agent.py
from dataclasses import dataclass
import asyncio
from anthropic import Anthropic  # Claude
import google.genai  # Gemini
import replicate  # Llama

@dataclass
class MultiAgentResult:
    planning: dict  # From Claude
    visual: dict    # From Gemini
    validation: dict  # From Llama

class MultiAgentOrchestrator:
    def __init__(self, api_keys: dict):
        self.claude = Anthropic(api_key=api_keys["anthropic"])
        self.gemini = google.genai.Client(api_key=api_keys["google"])
        self.llama_api = api_keys["replicate"]
    
    async def get_expert_opinions(self, parsed_workout: dict) -> MultiAgentResult:
        """Get recommendations from 3 experts in parallel"""
        
        results = await asyncio.gather(
            self._claude_planning(parsed_workout),
            self._gemini_visual(parsed_workout),
            self._llama_validation(parsed_workout),
        )
        
        return MultiAgentResult(
            planning=results[0],
            visual=results[1],
            validation=results[2],
        )
    
    async def _claude_planning(self, workout: dict) -> dict:
        """Claude: workout intent and visual metaphor"""
        response = self.claude.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": f"Workout: {workout}. What's the intent and visual metaphor?"
            }]
        )
        return {"intent": response.content[0].text}
    
    async def _gemini_visual(self, workout: dict) -> dict:
        """Gemini: visual prototype and styling"""
        response = self.gemini.models.generate_content(
            model="models/gemini-2.5-pro",
            contents=f"Design visual for: {workout}",
            config={"temperature": 0.7}
        )
        return {"visual_style": response.text}
    
    async def _llama_validation(self, workout: dict) -> dict:
        """Llama: movement validation and scaling"""
        output = replicate.run(
            "meta/llama-2-70b-chat:02e509c789964a7ea8736978a0e19d7d7f1091594a0514c4a3729d84518e9b13",
            input={"prompt": f"Validate workout: {workout}"}
        )
        return {"validation": "".join(output)}
    
    def synthesize_consensus(self, opinions: MultiAgentResult) -> str:
        """Merge expert opinions into single prompt"""
        prompt = f"""
Given expert opinions:

Planning (Claude):
{opinions.planning['intent']}

Visual (Gemini):
{opinions.visual['visual_style']}

Validation (Llama):
{opinions.validation['validation']}

Generate a final workout poster prompt that combines all insights.
"""
        return prompt
```

```python
# nodes.py - TIER 4 (use orchestrator)
async def multi_agent_node(state: PosterState) -> PosterState:
    parsed = state.get("parsed_workout", {})
    
    orchestrator = MultiAgentOrchestrator(api_keys={
        "anthropic": state["api_key"],
        "google": state["api_key"],
        "replicate": os.environ.get("REPLICATE_API_TOKEN"),
    })
    
    # Get all 3 expert opinions
    opinions = await orchestrator.get_expert_opinions(parsed)
    
    # Synthesize into single prompt
    final_prompt = orchestrator.synthesize_consensus(opinions)
    
    return {
        "multi_agent_opinions": {
            "planning": opinions.planning,
            "visual": opinions.visual,
            "validation": opinions.validation,
        },
        "final_graphic_prompt": final_prompt,
    }
```

```python
# NEW: human_loop.py - Feedback collection
from typing import Optional

@dataclass
class ReviewTask:
    image_id: str
    image_path: str
    critic_score: int
    questions: list[str]
    quick_actions: list[str]

@dataclass
class ReviewFeedback:
    image_id: str
    human_score: int
    approved: bool
    issues: list[str]
    feedback_text: str

class HumanFeedbackCollector:
    def should_review(self, critic_score: int) -> bool:
        """Flag borderline cases for human review"""
        return 70 <= critic_score < 90
    
    def create_review_task(self, image: dict) -> ReviewTask:
        """Create task for coach to review"""
        return ReviewTask(
            image_id=image["date"],
            image_path=image["path"],
            critic_score=image["critic_score"],
            questions=[
                "Movements rendered accurately?",
                "Weights and reps visible?",
                "Layout professional?",
                "Any hallucinations or errors?",
            ],
            quick_actions=[
                "✓ Approve",
                "~ Minor fixes",
                "✗ Reject",
            ],
        )
    
    async def collect_feedback(self, task: ReviewTask) -> Optional[ReviewFeedback]:
        """Wait for coach feedback (with timeout)"""
        # In real implementation: webhook, queue, etc.
        feedback = await wait_for_coach_review(task, timeout=3600)
        return feedback
    
    def store_for_training(self, feedback: ReviewFeedback):
        """Save for fine-tuning"""
        database.insert("training_samples", {
            "image_id": feedback.image_id,
            "human_score": feedback.human_score,
            "approved": feedback.approved,
            "issues": feedback.issues,
            "timestamp": datetime.now(),
        })
```

```python
# graph.py - TIER 4 (with human loop)
def _compile_graph():
    workflow = StateGraph(PosterState)
    
    # ... existing nodes ...
    
    workflow.add_node("multi_agent", multi_agent_node)
    workflow.add_node("human_feedback", human_feedback_node)
    
    workflow.add_edge("parser", "multi_agent")
    workflow.add_edge("validator", lambda s: "human_feedback" if s.get("needs_review") else "end")
```

**Result:**
```
Raw WOD
  ├→ Claude: "Intent is sprint + skill"
  ├→ Gemini: "Dark background, emphasize speed"
  └→ Llama: "Turkish Get-Up needs tall demonstration"
      ↓
  Final Prompt: Combines all 3 insights
      ↓
  Generate image
      ↓
  Borderline? (70-85 score) → Human reviews
      ↓
  Collect feedback → Store for training
      ↓
  Daily fine-tuning job updates models
```

---

## Summary

| Tier | Code Change | Complexity | Time |
|------|------------|-----------|------|
| **Tier 1** | Split schemas into 3 | Low | 2 weeks |
| **Tier 2** | Add refinement node + stricter routing | Medium | 3 weeks |
| **Tier 3** | Add deterministic parser, simplify LLMs | Medium-High | 6 weeks |
| **Tier 4** | Multi-LLM orchestration + human loop | High | 12 weeks |


from __future__ import annotations

from pathlib import Path
from typing import Any

from .nodes import (
    architect_node,
    designer_node,
    editor_node,
    generator_node,
    reasoning_node,
    should_retry,
    validation_node,
)
from .state import PosterState


def _compile_graph():
    try:
        from langgraph.graph import END, StateGraph
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("langgraph is not installed. Install it to enable LANGGRAPH_ENABLED mode.") from exc

    workflow = StateGraph(PosterState)
    workflow.add_node("reasoning", reasoning_node)
    workflow.add_node("editor", editor_node)
    workflow.add_node("architect", architect_node)
    workflow.add_node("designer", designer_node)
    workflow.add_node("generator", generator_node)
    workflow.add_node("validator", validation_node)

    workflow.set_entry_point("reasoning")
    workflow.add_edge("reasoning", "editor")
    workflow.add_edge("editor", "architect")
    workflow.add_edge("architect", "designer")
    workflow.add_edge("designer", "generator")
    workflow.add_edge("generator", "validator")

    workflow.add_conditional_edges(
        "validator",
        should_retry,
        {
            "retry": "reasoning",
            "success": END,
            "fail": END,
        },
    )

    return workflow.compile()


def run_poster_pipeline(
    *,
    raw_wod: dict[str, Any],
    output_path: Path,
    api_key: str,
    model: str,
    aspect_ratio: str,
    max_retries_api: int,
    max_retry_delay_seconds: float,
    retry_jitter_ratio: float,
    max_validation_retries: int = 3,
) -> dict[str, Any]:
    """Run the LangGraph poster pipeline and return final state."""
    graph = _compile_graph()
    initial_state: PosterState = {
        "raw_wod": raw_wod,
        "output_path": str(output_path),
        "api_key": api_key,
        "model": model,
        "aspect_ratio": aspect_ratio,
        "max_retries_api": max_retries_api,
        "max_retry_delay_seconds": max_retry_delay_seconds,
        "retry_jitter_ratio": retry_jitter_ratio,
        "retry_count": 0,
        "max_retries": max_validation_retries,
        "is_valid": False,
        "error_log": [],
    }

    result = graph.invoke(initial_state)
    return dict(result)

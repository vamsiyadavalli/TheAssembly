"""LangGraph-based poster orchestration package."""

__all__ = ["run_poster_pipeline"]


def run_poster_pipeline(*args, **kwargs):
	"""Lazy import wrapper so local tools remain importable without langgraph installed."""
	from .graph import run_poster_pipeline as _run_poster_pipeline

	return _run_poster_pipeline(*args, **kwargs)

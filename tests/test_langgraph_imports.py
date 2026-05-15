from __future__ import annotations


def test_graph_module_imports_cleanly() -> None:
    from theassembly.langgraph_pipeline import graph

    assert hasattr(graph, "run_poster_pipeline")

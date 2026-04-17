"""LangGraph state graph for the Phase B translation loop.

Wires all node functions into a compilable StateGraph. Two compiled graphs are
exposed:
- ``translation_graph``: no checkpointer, for direct CLI use (``oxidant phase-b``)
- ``build_checkpointed_graph(db_path)``: SqliteSaver checkpointer for ``oxidant serve``
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from oxidant.graph.nodes import (
    build_context,
    escalate_node,
    invoke_agent,
    pick_next_node,
    queue_for_review,
    retry_node,
    route_after_supervisor,
    route_after_verify,
    supervisor_node,
    update_manifest,
    verify,
)
from oxidant.graph.state import OxidantState


def _route_pick(state: OxidantState) -> str:
    return "done" if state.get("done") else "continue"


def build_graph(checkpointer=None) -> object:
    """Construct and compile the Phase B LangGraph state graph.

    Args:
        checkpointer: Optional LangGraph checkpointer (e.g. SqliteSaver).
                      Pass None for CLI usage; pass a SqliteSaver for ``oxidant serve``.
    """
    graph: StateGraph = StateGraph(OxidantState)

    graph.add_node("pick_next_node", pick_next_node)
    graph.add_node("build_context", build_context)
    graph.add_node("invoke_agent", invoke_agent)
    graph.add_node("verify", verify)
    graph.add_node("retry_node", retry_node)
    graph.add_node("escalate_node", escalate_node)
    graph.add_node("supervisor_node", supervisor_node)
    graph.add_node("update_manifest", update_manifest)
    graph.add_node("queue_for_review", queue_for_review)

    graph.set_entry_point("pick_next_node")

    graph.add_conditional_edges(
        "pick_next_node",
        _route_pick,
        {"continue": "build_context", "done": END},
    )
    graph.add_edge("build_context", "invoke_agent")
    graph.add_edge("invoke_agent", "verify")
    graph.add_conditional_edges(
        "verify",
        route_after_verify,
        {
            "update_manifest": "update_manifest",
            "retry": "retry_node",
            "escalate": "escalate_node",
            "supervisor": "supervisor_node",
        },
    )
    graph.add_edge("retry_node", "build_context")
    graph.add_edge("escalate_node", "build_context")
    graph.add_conditional_edges(
        "supervisor_node",
        route_after_supervisor,
        {
            "build_context": "build_context",
            "queue_for_review": "queue_for_review",
        },
    )
    graph.add_edge("update_manifest", "pick_next_node")
    graph.add_edge("queue_for_review", "pick_next_node")

    return graph.compile(checkpointer=checkpointer)


def build_checkpointed_graph(db_path: str) -> object:
    """Build a graph with SqliteSaver for use by ``oxidant serve``.

    Args:
        db_path: Absolute path to the SQLite checkpoint file (created if absent).
    """
    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver
    conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return build_graph(checkpointer=checkpointer)


# Compiled graph without checkpointer — used by ``oxidant phase-b`` CLI
translation_graph = build_graph()

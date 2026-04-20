"""LangGraph construction and checkpoint configuration"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

from langgraph.graph import END, StateGraph

from agent.nodes import investigate_node, plan_node, report_node, verify_node
from agent.state import InvestigationState
from agent.tools import InvestigationTools


@contextmanager
def _checkpointer_context() -> Iterator[Any]:
    checkpoint_uri = os.getenv("CHECKPOINT_URI", "").strip()

    if checkpoint_uri:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver

            with PostgresSaver.from_conn_string(checkpoint_uri) as saver:
                yield saver
                return
        except Exception:
            pass

    from langgraph.checkpoint.memory import MemorySaver

    yield MemorySaver()


def build_agent_graph(tools: InvestigationTools):
    graph = StateGraph(InvestigationState)

    graph.add_node("plan", plan_node)
    graph.add_node("investigate", lambda state: investigate_node(state, tools))
    graph.add_node("verify", verify_node)
    graph.add_node("report", report_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "investigate")
    graph.add_edge("investigate", "verify")
    graph.add_conditional_edges(
        "verify",
        lambda state: "report" if state.get("done", False) else "investigate",
        {"report": "report", "investigate": "investigate"},
    )
    graph.add_edge("report", END)

    return graph


def compile_agent_graph(tools: InvestigationTools):
    graph = build_agent_graph(tools)
    checkpointer_ctx = _checkpointer_context()
    checkpointer = checkpointer_ctx.__enter__()
    compiled = graph.compile(checkpointer=checkpointer)

    # Attach context manager for explicit cleanup by caller
    setattr(compiled, "_siren_checkpointer_ctx", checkpointer_ctx)
    return compiled

"""LangGraph construction and checkpoint configuration"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

from langgraph.graph import END, StateGraph

from agent.nodes import (
    investigate_step,
    plan_investigation,
    should_continue,
    verify_hypothesis,
    write_report,
)
from agent.state import InvestigationState


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


def build_investigation_graph():
    graph = StateGraph(InvestigationState)

    graph.add_node("plan", plan_investigation)
    graph.add_node("investigate", investigate_step)
    graph.add_node("verify", verify_hypothesis)
    graph.add_node("report", write_report)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "investigate")
    graph.add_conditional_edges(
        "investigate",
        should_continue,
        {"investigate": "investigate", "verify": "verify"},
    )
    graph.add_edge("verify", "report")
    graph.add_edge("report", END)

    with _checkpointer_context() as checkpointer:
        return graph.compile(checkpointer=checkpointer)


# Backward-compatible alias
build_agent_graph = build_investigation_graph

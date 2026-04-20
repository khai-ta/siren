"""LangGraph construction and checkpoint configuration"""

from __future__ import annotations

import os
from typing import Any

from langgraph.graph import END, StateGraph

from agent.nodes import (
    investigate_step,
    plan_investigation,
    should_continue,
    verify_hypothesis,
    write_report,
)
from agent.state import InvestigationState


def build_investigation_graph(checkpointer: Any = None):
    """Build and compile the investigation graph with an externally managed checkpointer"""
    from langgraph.checkpoint.memory import MemorySaver

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

    return graph.compile(checkpointer=checkpointer or MemorySaver())


# Backward-compatible alias
build_agent_graph = build_investigation_graph

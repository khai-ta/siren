"""Public entrypoint for running an agent investigation"""

from __future__ import annotations

import uuid
from typing import Any

from agent.graph import build_investigation_graph
from agent.state import InvestigationState


def run_investigation(
    anomalies: list[dict[str, Any]],
    origin_service: str,
    window_start: str,
    window_end: str,
    incident_id: str | None = None,
    max_steps: int = 15,
) -> dict[str, Any]:
    """Run a full agent investigation and return the final state"""
    graph = build_investigation_graph()
    incident_id = incident_id or str(uuid.uuid4())[:12]

    initial_state: InvestigationState = {
        "incident_id": incident_id,
        "anomalies": anomalies,
        "origin_service": origin_service,
        "window_start": window_start,
        "window_end": window_end,
        "investigation_plan": [],
        "current_step": 0,
        "hypotheses": [],
        "tool_history": [],
        "evidence_ledger": {},
        "max_steps": max_steps,
        "should_conclude": False,
        "final_root_cause": None,
        "final_confidence": None,
        "final_report": None,
    }

    config = {"configurable": {"thread_id": incident_id}}
    final_state = graph.invoke(initial_state, config=config)

    return dict(final_state)


# Backward-compatible alias while the rest of the codebase migrates
run_agent_investigation = run_investigation

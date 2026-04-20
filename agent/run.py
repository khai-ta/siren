"""Public entrypoint for running an agent investigation"""

from __future__ import annotations

import os
import uuid
from typing import Any

from langchain_community.callbacks.manager import get_openai_callback

from agent.graph import build_investigation_graph
from agent.state import InvestigationState


def _invoke_with_checkpointer(initial_state: InvestigationState, config: dict) -> dict[str, Any]:
    """Build graph + invoke, keeping Postgres connection alive for the full run"""
    checkpoint_uri = os.getenv("CHECKPOINT_URI", "").strip()

    with get_openai_callback() as cb:
        if checkpoint_uri:
            try:
                from langgraph.checkpoint.postgres import PostgresSaver

                with PostgresSaver.from_conn_string(checkpoint_uri) as saver:
                    saver.setup()
                    graph = build_investigation_graph(saver)
                    final_state = dict(graph.invoke(initial_state, config=config))
            except Exception as error:
                print(f"Postgres checkpointer unavailable ({error}) — falling back to in-memory")
                graph = build_investigation_graph()
                final_state = dict(graph.invoke(initial_state, config=config))
        else:
            graph = build_investigation_graph()
            final_state = dict(graph.invoke(initial_state, config=config))

    _log_token_usage(cb)
    return final_state


def _log_token_usage(cb) -> None:
    """Print token usage and cost estimate"""
    print(f"\nTokens used: {cb.total_tokens} (input: {cb.prompt_tokens}, output: {cb.completion_tokens})")
    print(f"Estimated cost: ${cb.total_cost:.4f}")


def run_investigation(
    anomalies: list[dict[str, Any]],
    origin_service: str,
    window_start: str,
    window_end: str,
    incident_id: str | None = None,
    max_steps: int = 15,
) -> dict[str, Any]:
    """Run a full agent investigation and return the final state"""
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
    return _invoke_with_checkpointer(initial_state, config)


# Backward-compatible alias while the rest of the codebase migrates
run_agent_investigation = run_investigation

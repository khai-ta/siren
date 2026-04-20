"""LangGraph nodes for planning, investigation, verification, and reporting"""

from __future__ import annotations

from typing import Any

from agent.state import HypothesisEntry, InvestigationState
from agent.tools import InvestigationTools


def _append_trace(state: InvestigationState, message: str) -> list[str]:
    trace = list(state.get("reasoning_trace", []))
    trace.append(message)
    return trace


def plan_node(state: InvestigationState) -> dict[str, Any]:
    focus = state.get("current_focus") or state["origin_service"]
    metric = state["anomalies"][0]["metric"] if state.get("anomalies") else "error_rate"
    hypothesis = f"{focus} is causing cascading failures via {metric} degradation"

    ledger = list(state.get("hypothesis_ledger", []))
    ledger.append(
        HypothesisEntry(
            hypothesis=hypothesis,
            evidence_for=[],
            evidence_against=[],
            confidence=0.35,
        )
    )

    return {
        "current_focus": focus,
        "hypothesis_ledger": ledger,
        "reasoning_trace": _append_trace(state, f"plan: focus on {focus}"),
    }


def investigate_node(state: InvestigationState, tools: InvestigationTools) -> dict[str, Any]:
    query = f"{state['current_focus']} incident hypothesis validation"
    retrieved, uncached_ms, cached_ms = tools.retrieve_evidence(
        query=query,
        anomalies=state["anomalies"],
        origin_service=state["origin_service"],
        window_start=state["window_start"],
        window_end=state["window_end"],
    )

    ledger = list(state.get("hypothesis_ledger", []))
    if ledger:
        latest = dict(ledger[-1])
        top_logs = [str(item.get("text", "")) for item in retrieved.get("top_logs", [])[:2]]
        top_traces = [str(item.get("text", "")) for item in retrieved.get("top_traces", [])[:1]]
        latest["evidence_for"] = [t for t in top_logs + top_traces if t]
        latest["evidence_against"] = []
        ledger[-1] = latest

    return {
        "query": query,
        "retrieved": retrieved,
        "uncached_latency_ms": uncached_ms,
        "cached_latency_ms": cached_ms,
        "step_count": int(state.get("step_count", 0)) + 1,
        "hypothesis_ledger": ledger,
        "reasoning_trace": _append_trace(state, "investigate: collected focused evidence"),
    }


def verify_node(state: InvestigationState) -> dict[str, Any]:
    ledger = list(state.get("hypothesis_ledger", []))
    confidence = float(state.get("confidence", 0.3))

    if ledger:
        evidence_count = len(ledger[-1].get("evidence_for", []))
        confidence = min(0.95, 0.3 + 0.12 * evidence_count)
        ledger[-1]["confidence"] = confidence

    blast_radius = list((state.get("retrieved") or {}).get("blast_radius", []))
    next_focus = state.get("current_focus", state["origin_service"])
    if confidence < 0.7 and blast_radius:
        next_focus = blast_radius[0]

    done = confidence >= 0.7 or int(state.get("step_count", 0)) >= int(state.get("max_steps", 6))

    return {
        "confidence": confidence,
        "done": done,
        "current_focus": next_focus,
        "hypothesis_ledger": ledger,
        "reasoning_trace": _append_trace(state, f"verify: confidence={confidence:.2f}"),
    }


def report_node(state: InvestigationState) -> dict[str, Any]:
    retrieved = state.get("retrieved", {})
    affected = ", ".join(retrieved.get("affected_services", [])) or "(none)"

    hypothesis = "No hypothesis recorded"
    if state.get("hypothesis_ledger"):
        hypothesis = state["hypothesis_ledger"][-1]["hypothesis"]

    report = (
        "## INCIDENT SUMMARY\n"
        f"Autonomous loop investigated {state['incident_name']} across multiple retrieval steps.\n\n"
        "## ROOT CAUSE\n"
        f"Most likely root cause: {state['origin_service']} with hypothesis '{hypothesis}'.\n\n"
        "## EVIDENCE FOR\n"
        + "\n".join(f"- {line}" for line in (state.get("hypothesis_ledger", [{}])[-1].get("evidence_for", [])[:4] or ["Evidence collected in retrieval output"]))
        + "\n\n"
        "## EVIDENCE AGAINST\n"
        + "\n".join(f"- {line}" for line in (state.get("hypothesis_ledger", [{}])[-1].get("evidence_against", [])[:3] or ["No strong contradictory evidence found in this setup loop"]))
        + "\n\n"
        "## CONFIDENCE\n"
        f"{int(float(state.get('confidence', 0.0)) * 100)}%\n\n"
        "## BLAST RADIUS\n"
        f"{affected}\n\n"
        "## NEXT ACTIONS\n"
        "1. Validate the hypothesis against fresh traces\n"
        "2. Confirm rollback or mitigation impact on latency and errors\n"
        "3. Add targeted alerting for first-failure indicators\n"
    )

    return {
        "final_report": report,
        "reasoning_trace": _append_trace(state, "report: finalized RCA output"),
    }

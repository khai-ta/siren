"""Build investigator prompts with delta-only state updates"""

from typing import Any

from agent.state import Hypothesis, InvestigationState
from processing.evidence_digest import build_evidence_digest


def build_investigator_prompt(state: InvestigationState) -> str:
    """Build a compressed prompt that sends only what's changed since last step

    Instead of re-sending all tool history and full hypothesis state every step,
    we send:
    - Compressed anomaly summary (one line per anomaly)
    - Hypothesis deltas (only status changes, confidence changes > 0.1)
    - Most recent 3 tool calls
    - Evidence digest (rolling summary)
    """
    sections: list[str] = []

    # Anomalies (always include — they're the core question)
    anomaly_lines = [
        f"- {a['service']} {a['metric']} z={float(a.get('zscore', 0)):.1f}"
        for a in state["anomalies"][:5]  # cap at 5 for token efficiency
    ]
    if len(state["anomalies"]) > 5:
        anomaly_lines.append(f"  (+{len(state['anomalies']) - 5} more anomalies)")
    sections.append("Anomalies:\n" + "\n".join(anomaly_lines))

    # Hypothesis status (compressed)
    if state["hypotheses"]:
        hypothesis_lines = []
        for h in state["hypotheses"]:
            status_icon = {"open": "?", "confirmed": "✓", "rejected": "✗"}.get(h["status"], "?")
            hypothesis_lines.append(
                f"{status_icon} {h['statement']} "
                f"(conf {h['confidence']:.0%}, {len(h['evidence_for'])}for/{len(h['evidence_against'])}against)"
            )
        sections.append("Hypotheses:\n" + "\n".join(hypothesis_lines))

    # Recent tool history (last 3 only)
    if state["tool_history"]:
        recent_tools = state["tool_history"][-3:]
        tool_lines = [
            f"Step {tc['step']}: {tc['tool_name']} → {tc['result_summary'][:100]}"
            for tc in recent_tools
        ]
        if len(state["tool_history"]) > 3:
            tool_lines.insert(0, f"(steps 1-{len(state['tool_history']) - 3} elided)")
        sections.append("Recent tools:\n" + "\n".join(tool_lines))

    # Evidence digest (rolling summary)
    sections.append(build_evidence_digest(state["evidence_ledger"]))

    # Step budget
    remaining = state["max_steps"] - state["current_step"]
    sections.append(f"Step {state['current_step'] + 1}/{state['max_steps']} ({remaining} remaining)")

    return "\n\n".join(sections)

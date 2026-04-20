"""Compress the evidence ledger into a rolling digest"""

from typing import Any


def build_evidence_digest(
    evidence_ledger: dict[str, dict[str, Any]],
    max_recent: int = 3,
) -> str:
    """Build a compressed summary of the evidence ledger for prompt inclusion

    The latest N pieces of evidence get full summaries. Older evidence gets
    one-line labels so the agent knows what's been checked without re-reading
    the full payloads
    """
    if not evidence_ledger:
        return "(no evidence gathered yet)"

    items = sorted(
        evidence_ledger.items(),
        key=lambda kv: int(kv[1].get("step", 0)),
    )

    recent = items[-max_recent:]
    older = items[:-max_recent] if len(items) > max_recent else []

    lines: list[str] = []

    if older:
        older_summary = ", ".join(
            f"{ev['tool']} (step {ev['step']})" for _, ev in older
        )
        lines.append(f"Prior evidence gathered: {older_summary}")

    if recent:
        lines.append("Recent evidence:")
        for ev_id, ev in recent:
            summary = _summarize_evidence_item(ev)
            lines.append(f"  [{ev_id}] step {ev['step']} {ev['tool']}: {summary}")

    return "\n".join(lines)


def _summarize_evidence_item(evidence: dict[str, Any]) -> str:
    """Produce a one-line summary of an evidence entry"""
    data = evidence.get("data")
    tool = evidence.get("tool", "")

    if isinstance(data, list):
        return f"list[{len(data)}]"
    if isinstance(data, dict):
        keys = list(data.keys())[:4]
        return f"dict with keys: {', '.join(keys)}"
    if isinstance(data, str):
        return data[:150].replace("\n", " ")
    return str(data)[:150]

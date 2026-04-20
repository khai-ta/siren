"""Condense trace spans into failure path digests"""

from collections import Counter
from typing import Any


def condense_trace_errors(spans: list[dict[str, Any]], max_examples: int = 3) -> str:
    """Turn a list of failing trace spans into a digest

    Input:  10 trace span dicts, each with trace_id, service, operation, status, duration_ms
    Output: "12 failing spans: 8 timeouts, 4 errors. Top operations:
             user_auth.database (5 timeouts, p99=2100ms)
             payment.database (3 timeouts, p99=2400ms)
             Example: trace abc12345 — auth→database timeout after 2100ms"
    """
    if not spans:
        return "no failing traces in window"

    statuses = Counter(s.get("status", "unknown") for s in spans)
    operations = Counter(s.get("operation", "unknown") for s in spans)

    header = f"{len(spans)} failing spans: " + ", ".join(
        f"{count} {status}s" for status, count in statuses.most_common()
    )

    # Top operations with peak latency
    top_ops: list[str] = []
    for op_name, count in operations.most_common(3):
        op_spans = [s for s in spans if s.get("operation") == op_name]
        max_duration = max((_safe_float(s.get("duration_ms")) or 0 for s in op_spans), default=0)
        top_ops.append(f"  {op_name} ({count} failures, peak={max_duration:.0f}ms)")

    # Include a couple of examples with trace_id truncated
    examples: list[str] = []
    for span in spans[:max_examples]:
        trace_id_short = str(span.get("trace_id", ""))[:8]
        service = span.get("service", "?")
        duration = _safe_float(span.get("duration_ms")) or 0
        status = span.get("status", "?")
        examples.append(f"  trace {trace_id_short} — {service} {status} after {duration:.0f}ms")

    sections = [header, "Top failing operations:"] + top_ops
    if examples:
        sections.extend(["Examples:"] + examples)

    return "\n".join(sections)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None

"""Convert metric baseline/peak dicts into agent-readable summaries"""

from typing import Any


def summarize_metrics(
    service: str,
    baseline: dict[str, Any],
    peak: dict[str, Any],
) -> str:
    """Produce a one-line summary highlighting what's anomalous

    Input:  baseline = {"error_rate_mean": 0.001, "latency_p99_mean": 30, ...}
            peak =     {"error_rate_peak": 0.012, "latency_p99_peak": 245, ...}
    Output: "database: error_rate 0.1%→1.2% (12×), latency_p99 30ms→245ms (8×)"
    """
    if not baseline or not peak:
        return f"{service}: no metric data available"

    parts: list[str] = []

    b_err = _safe_float(baseline.get("error_rate_mean"))
    p_err = _safe_float(peak.get("error_rate_peak"))
    if b_err and p_err and p_err > b_err * 1.5:
        ratio = p_err / max(b_err, 1e-9)
        parts.append(f"error_rate {b_err*100:.2f}%→{p_err*100:.2f}% ({ratio:.1f}×)")

    b_p99 = _safe_float(baseline.get("latency_p99_mean"))
    p_p99 = _safe_float(peak.get("latency_p99_peak"))
    if b_p99 and p_p99 and p_p99 > b_p99 * 1.5:
        ratio = p_p99 / max(b_p99, 1e-9)
        parts.append(f"latency_p99 {b_p99:.0f}ms→{p_p99:.0f}ms ({ratio:.1f}×)")

    b_mem = _safe_float(baseline.get("memory_mean"))
    p_mem = _safe_float(peak.get("memory_peak"))
    if b_mem and p_mem and p_mem > b_mem * 1.2:
        ratio = p_mem / max(b_mem, 1e-9)
        parts.append(f"memory {b_mem:.0f}%→{p_mem:.0f}% ({ratio:.1f}×)")

    b_rps = _safe_float(baseline.get("rps_mean"))
    p_rps = _safe_float(peak.get("rps_min"))  # note: rps min (traffic drop signal)
    if b_rps and p_rps and p_rps < b_rps * 0.7:
        ratio = p_rps / max(b_rps, 1e-9)
        parts.append(f"rps dropped {b_rps:.0f}→{p_rps:.0f} ({ratio:.1f}×)")

    if not parts:
        return f"{service}: metrics within normal range"

    return f"{service}: " + ", ".join(parts)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None

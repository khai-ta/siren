"""Summarize metric dicts into agent-actionable insights

Raw metric dicts contain 8 numeric fields per service. Agents need:
"latency peaked 8× baseline, error rate at 12× baseline". One sentence
"""

from __future__ import annotations

from typing import Any


def summarize_metrics(metrics: dict[str, Any]) -> str:
    """Convert baseline/peak metrics dict to one-line summary

    Args:
        metrics: Dict with 'baseline' and 'peak' keys containing metric dicts

    Returns:
        One-sentence summary of anomalies (5-10 tokens vs 50+ for raw dict)
    """
    pass

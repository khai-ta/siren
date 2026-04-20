"""Condense trace spans into failure path digests

Traces often contain 50+ spans with repetitive structure. Extract the error path:
which spans failed, where, and what the error was
"""

from __future__ import annotations

from typing import Any


def condense_traces(traces: list[dict[str, Any]]) -> list[str]:
    """Extract failure paths from trace spans

    Args:
        traces: Raw trace span dicts

    Returns:
        List of failure path summaries (one per error path)
    """
    pass

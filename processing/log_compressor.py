"""Compress raw log messages into dense, agent-ready representations

Raw logs have 85% structural repetition (service, instance, trace_id, level fields).
This module extracts signal: error messages, anomalies, state changes
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any


# Patterns extracted from LOG_TEMPLATES — used to strip repetitive suffixes
REDUNDANT_PATTERNS = [
    r"attempt \d+/\d+",
    r"trace_id=[a-f0-9]+",
    r" - table: \w+",
]


def compress_log_entry(log_row: dict[str, Any]) -> str:
    """Convert a raw log dict to a short string

    Input:  {"timestamp": "2026-04-19T21:44:03", "service": "database",
             "level": "ERROR", "message": '{"level":"ERROR",...,"event":"Query timeout after 2500ms"}'}
    Output: "[21:44:03] database ERROR: Query timeout after 2500ms"
    """
    timestamp = log_row.get("timestamp", "")
    time_part = timestamp.split("T")[1][:8] if "T" in timestamp else timestamp[:8]
    service = log_row.get("service", "?")
    level = log_row.get("level", "INFO")

    message = log_row.get("message", "")
    event = _extract_event_text(message)

    # Strip redundant suffixes that don't affect diagnosis
    for pattern in REDUNDANT_PATTERNS:
        event = re.sub(pattern, "", event).strip()

    return f"[{time_part}] {service} {level}: {event}"


def _extract_event_text(message: str) -> str:
    """Pull the human-readable 'event' field out of a structured log JSON"""
    if not message.startswith("{"):
        return message[:120]
    try:
        payload = json.loads(message)
        return str(payload.get("event", message))[:120]
    except json.JSONDecodeError:
        return message[:120]


def cluster_similar_logs(logs: list[dict[str, Any]], max_per_cluster: int = 3) -> list[str]:
    """Group similar log messages and keep at most N representatives per cluster

    A service that logs 'Connection pool exhausted' 50 times only needs
    to show 3 of them to the agent — the pattern is the signal
    """
    compressed = [compress_log_entry(log) for log in logs]

    # Cluster by (service, level, first 8 words of event)
    def cluster_key(compressed_log: str) -> str:
        parts = compressed_log.split(": ", 1)
        prefix = parts[0]  # "[time] service LEVEL"
        content = parts[1] if len(parts) > 1 else ""
        # Normalize numbers to %d so "Query timeout after 2500ms" and "after 3200ms" cluster together
        normalized = re.sub(r"\d+(\.\d+)?", "%d", content)
        # Take service+level from prefix, first 8 tokens of normalized content
        service_level = " ".join(prefix.split()[1:])
        content_key = " ".join(normalized.split()[:8])
        return f"{service_level}|{content_key}"

    clusters: dict[str, list[str]] = {}
    for log in compressed:
        key = cluster_key(log)
        clusters.setdefault(key, []).append(log)

    result: list[str] = []
    for key, cluster in clusters.items():
        # Keep first, middle, last — or all if fewer than max_per_cluster
        if len(cluster) <= max_per_cluster:
            result.extend(cluster)
        else:
            result.extend([cluster[0], cluster[len(cluster) // 2], cluster[-1]])
            result.append(f"  ... ({len(cluster) - 3} more similar)")

    return result


def estimate_token_savings(original_logs: list[dict], compressed: list[str]) -> dict[str, int]:
    """Report before/after token estimates (rough: ~4 chars per token)"""
    original_chars = sum(len(json.dumps(log)) for log in original_logs)
    compressed_chars = sum(len(log) for log in compressed)
    return {
        "original_tokens_est": original_chars // 4,
        "compressed_tokens_est": compressed_chars // 4,
        "reduction_pct": round((1 - compressed_chars / max(original_chars, 1)) * 100, 1),
    }

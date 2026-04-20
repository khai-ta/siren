"""Tool definitions for the autonomous investigation agent"""

from __future__ import annotations

import functools
import hashlib
import json
import os
from typing import Any

from langchain_core.tools import tool
from retrieval.orchestrator import SirenQueryEngine


_engine = SirenQueryEngine()
_CACHE_TTL = int(os.getenv("TOOL_CACHE_TTL", "300"))


def _redis():
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None
    try:
        import redis
        return redis.from_url(url)
    except Exception:
        return None


def _cache(ttl: int = _CACHE_TTL):
    """Decorator that caches tool results in Redis keyed by function name + kwargs"""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            r = _redis()
            if r is None:
                return fn(*args, **kwargs)
            raw = json.dumps(
                {"fn": fn.__name__, "args": list(args), "kwargs": kwargs},
                sort_keys=True,
                default=str,
            )
            key = f"siren:tool:{hashlib.sha256(raw.encode()).hexdigest()[:20]}"
            try:
                hit = r.get(key)
                if hit:
                    return json.loads(hit)
            except Exception:
                pass
            result = fn(*args, **kwargs)
            try:
                r.setex(key, ttl, json.dumps(result, default=str))
            except Exception:
                pass
            return result
        return wrapper
    return decorator


@tool
@_cache()
def query_logs(
    service: str,
    query: str,
    window_start: str,
    window_end: str,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Search logs for a service in a time window"""
    candidates = _engine.logs_store.search(
        query=query,
        top_k=50,
        filter={
            "service": service,
            "timestamp": {"$gte": window_start, "$lte": window_end},
        },
    )
    return _engine.reranker.rerank(query, candidates, top_n=top_k)


@tool
@_cache()
def get_metrics(
    service: str,
    window_start: str,
    window_end: str,
) -> dict[str, Any]:
    """Get baseline and peak metrics for a service"""
    # Convert relative window_start if needed
    from datetime import datetime, timedelta
    def resolve_timestamp(ts):
        if isinstance(ts, str):
            if ts == "now":
                return datetime.utcnow().isoformat()
            if ts.startswith("now-"):
                # Only supports minutes (e.g., now-30m)
                if ts.endswith("m"):
                    mins = int(ts[4:-1])
                    return (datetime.utcnow() - timedelta(minutes=mins)).isoformat()
                elif ts.endswith("h"):
                    hours = int(ts[4:-1])
                    return (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        return ts

    baseline_end = resolve_timestamp(window_start)
    window_start_res = resolve_timestamp(window_start)
    window_end_res = resolve_timestamp(window_end)
    return {
        "baseline": _engine.metrics.get_baseline(service, baseline_end),
        "peak": _engine.metrics.get_peak(service, window_start_res, window_end_res),
    }


@tool
def get_dependencies(service: str) -> list[str]:
    """Get services this service depends on"""
    return _engine.graph.get_dependencies(service)


@tool
@_cache()
def search_runbook(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    """Search runbooks for failure modes and remediations"""
    candidates = _engine.docs_store.search(query=query, top_k=10)
    return _engine.reranker.rerank(query, candidates, top_n=top_k)


INVESTIGATION_TOOLS = [
    query_logs,
    get_metrics,
    get_dependencies,
    search_runbook,
]

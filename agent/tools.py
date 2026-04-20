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
            raw = json.dumps({"fn": fn.__name__, **kwargs}, sort_keys=True, default=str)
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
    """Search logs semantically for a specific service in a time window

    Use this when you need to find log messages related to a specific hypothesis,
    like searching for 'connection pool exhausted' in database logs
    """
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
    """Get baseline and peak metrics for a service during an incident window

    Returns error_rate, latency_p99, rps, and memory for both pre-incident baseline
    means and in-window peak values. Use this to verify or reject hypotheses
    """
    return {
        "baseline": _engine.metrics.get_baseline(service, window_start),
        "peak": _engine.metrics.get_peak(service, window_start, window_end),
    }


@tool
def get_dependencies(service: str) -> list[str]:
    """Get services this service directly depends on

    Use this to understand what could cause a service to fail
    """
    return _engine.graph.get_dependencies(service)


@tool
def get_callers(service: str) -> list[str]:
    """Get services that directly call this service

    Use this to understand blast radius for an upstream failure
    """
    return _engine.graph.get_callers(service)


@tool
def get_blast_radius(service: str) -> list[str]:
    """Get all services transitively affected if this service fails

    Use this once you have a root cause hypothesis to estimate full impact
    """
    return _engine.graph.get_blast_radius(service)


@tool
@_cache()
def search_runbook(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    """Search service runbooks for matching failure modes

    Use this to find documented causes and remediations for observed symptoms
    """
    candidates = _engine.docs_store.search(query=query, top_k=10)
    return _engine.reranker.rerank(query, candidates, top_n=top_k)


@tool
@_cache()
def get_trace_errors(
    service: str,
    window_start: str,
    window_end: str,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Get trace spans with errors or timeouts for a service in a time window

    Use this to inspect failed request paths and error messages
    """
    candidates = _engine.traces_store.search(
        query=f"{service} error timeout",
        top_k=50,
        filter={
            "service": service,
            "status": {"$in": ["error", "timeout"]},
            "timestamp": {"$gte": window_start, "$lte": window_end},
        },
    )
    return candidates[:top_k]


INVESTIGATION_TOOLS = [
    query_logs,
    get_metrics,
    get_dependencies,
    get_callers,
    get_blast_radius,
    search_runbook,
    get_trace_errors,
]

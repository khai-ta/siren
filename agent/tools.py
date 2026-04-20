"""Tools the agent can call during investigation"""

from __future__ import annotations

import time
from typing import Any

from retrieval.orchestrator import SirenQueryEngine


class InvestigationTools:
    """Thin tool wrapper around the Slice 3 retrieval engine"""

    def __init__(self, engine: SirenQueryEngine) -> None:
        self.engine = engine

    def retrieve_evidence(
        self,
        *,
        query: str,
        anomalies: list[dict[str, Any]],
        origin_service: str,
        window_start: str,
        window_end: str,
    ) -> tuple[dict[str, Any], float, float]:
        uncached_start = time.perf_counter()
        retrieved = self.engine.retrieve(
            query=query,
            anomalies=anomalies,
            origin_service=origin_service,
            window_start=window_start,
            window_end=window_end,
        )
        uncached_ms = (time.perf_counter() - uncached_start) * 1000.0

        cached_start = time.perf_counter()
        _ = self.engine.retrieve(
            query=query,
            anomalies=anomalies,
            origin_service=origin_service,
            window_start=window_start,
            window_end=window_end,
        )
        cached_ms = (time.perf_counter() - cached_start) * 1000.0

        return retrieved, uncached_ms, cached_ms

"""LlamaIndex orchestration that ties all stores together"""

from typing import Any, Dict, List

from llama_index.core import Settings
from llama_index.embeddings.openai import OpenAIEmbedding

from .cache import RetrievalCache
from .neo4j_store import Neo4jStore
from .pinecone_store import PineconeStore
from .reranker import CohereReranker
from .timescale_store import TimescaleStore

Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")


class SirenQueryEngine:
    def __init__(self) -> None:
        self.logs_store = PineconeStore("siren-logs")
        self.traces_store = PineconeStore("siren-traces")
        self.docs_store = PineconeStore("siren-docs")
        self.graph = Neo4jStore()
        self.metrics = TimescaleStore()
        self.reranker = CohereReranker()
        self.cache = RetrievalCache()

    def _search_logs_with_window(
        self,
        *,
        query: str,
        window_start: str,
        window_end: str,
        source: str,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        candidates = self.logs_store.search(
            query=query,
            top_k=top_k,
            filter={
                "source": {"$eq": source},
                "timestamp": {"$gte": window_start, "$lte": window_end},
            },
        )
        if candidates:
            return candidates

        fallback_filter: Dict[str, Any] = {"source": {"$eq": source}}
        if source == "log":
            fallback_filter = {
                "timestamp": {"$gte": window_start, "$lte": window_end},
            }

        return self.logs_store.search(query=query, top_k=top_k, filter=fallback_filter)

    def _top_reranked(self, query: str, candidates: List[Dict[str, Any]], top_n: int) -> List[Dict[str, Any]]:
        return self.reranker.rerank(query, candidates, top_n=top_n)

    def retrieve(
        self,
        query: str,
        anomalies: List[Dict],
        origin_service: str,
        window_start: str,
        window_end: str,
    ) -> Dict[str, Any]:
        cached = self.cache.get("retrieve", query, origin_service, window_start, window_end)
        if cached is not None:
            return cached

        log_candidates = self._search_logs_with_window(
            query=query,
            window_start=window_start,
            window_end=window_end,
            source="log",
            top_k=50,
        )
        trace_candidates = self._search_logs_with_window(
            query=query,
            window_start=window_start,
            window_end=window_end,
            source="trace",
            top_k=30,
        )

        doc_candidates = self.docs_store.search(query=query, top_k=20)

        top_logs = self._top_reranked(query, log_candidates, top_n=15)
        top_traces = self._top_reranked(query, trace_candidates, top_n=10)
        top_docs = self._top_reranked(query, doc_candidates, top_n=5)

        blast_radius = self.graph.get_blast_radius(origin_service)
        cascade_paths = self.graph.get_critical_cascade_paths(origin_service)

        affected = [origin_service] + blast_radius
        metrics_summary: Dict[str, Dict[str, Any]] = {}
        from datetime import datetime, timedelta
        def resolve_timestamp(ts):
            if isinstance(ts, str):
                if ts == "now":
                    return datetime.utcnow().isoformat()
                if ts.startswith("now-"):
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
        for service in affected:
            metrics_summary[service] = {
                "baseline": self.metrics.get_baseline(service, baseline_end),
                "peak": self.metrics.get_peak(service, window_start_res, window_end_res),
            }

        result: Dict[str, Any] = {
            "anomalies": anomalies,
            "origin_service": origin_service,
            "affected_services": affected,
            "blast_radius": blast_radius,
            "cascade_paths": cascade_paths,
            "top_logs": top_logs,
            "top_traces": top_traces,
            "top_docs": top_docs,
            "metrics_summary": metrics_summary,
        }

        self.cache.set("retrieve", query, origin_service, window_start, window_end, value=result)
        return result


class RetrievalOrchestrator(SirenQueryEngine):
    """Backward-compatible alias for the retrieval query engine"""


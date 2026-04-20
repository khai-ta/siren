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
        self.docs_store = PineconeStore("siren-docs")
        self.graph = Neo4jStore()
        self.metrics = TimescaleStore()
        self.reranker = CohereReranker()
        self.cache = RetrievalCache()

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

        log_candidates = self.logs_store.search(
            query=query,
            top_k=50,
            filter={
                "source": {"$eq": "log"},
                "timestamp": {"$gte": window_start, "$lte": window_end},
            },
        )
        if not log_candidates:
            log_candidates = self.logs_store.search(
                query=query,
                top_k=50,
                filter={"timestamp": {"$gte": window_start, "$lte": window_end}},
            )

        trace_candidates = self.logs_store.search(
            query=query,
            top_k=30,
            filter={
                "source": {"$eq": "trace"},
                "timestamp": {"$gte": window_start, "$lte": window_end},
            },
        )
        if not trace_candidates:
            trace_candidates = self.logs_store.search(query=query, top_k=30, filter={"source": {"$eq": "trace"}})

        doc_candidates = self.docs_store.search(query=query, top_k=20)

        top_logs = self.reranker.rerank(query, log_candidates, top_n=15)
        top_traces = self.reranker.rerank(query, trace_candidates, top_n=10)
        top_docs = self.reranker.rerank(query, doc_candidates, top_n=5)

        blast_radius = self.graph.get_blast_radius(origin_service)
        cascade_paths = self.graph.get_critical_cascade_paths(origin_service)

        affected = [origin_service] + blast_radius
        metrics_summary: Dict[str, Dict[str, Any]] = {}
        for service in affected:
            metrics_summary[service] = {
                "baseline": self.metrics.get_baseline(service, window_start),
                "peak": self.metrics.get_peak(service, window_start, window_end),
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


"""Batch indexer scaffold"""

from pathlib import Path
from typing import Dict, Tuple

from .metric_store import MetricStore
from .vector_store import VectorStore


class RetrievalIndexer:
    """Placeholder ingestion orchestrator for future retrieval indexing"""

    def __init__(self, vector_store: VectorStore, metric_store: MetricStore) -> None:
        self.vector_store = vector_store
        self.metric_store = metric_store

    @staticmethod
    def _paths_for_bundle(metrics_csv: str) -> Tuple[Path, Path, Path]:
        metrics_path = Path(metrics_csv).resolve()
        logs_path = metrics_path.parent.parent / "logs" / metrics_path.name
        traces_path = metrics_path.parent.parent / "traces" / metrics_path.name
        return metrics_path, logs_path, traces_path

    def index_runbooks(self, docs_dir: str) -> int:
        return 0

    def index_incident_bundle(self, metrics_csv: str) -> Dict[str, int]:
        return {
            "metrics_rows": 0,
            "log_rows": 0,
        }

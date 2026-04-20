"""Batch ingestion across Pinecone, TimescaleDB, and Neo4j"""

import csv
import re
from pathlib import Path
from typing import Any, Dict


def index_incident(
    metrics_csv: str,
    logs_csv: str,
    docs_dir: str,
    orchestrator: Any,
    traces_csv: str | None = None,
) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    counts["metrics"] = orchestrator.metrics.ingest_csv(metrics_csv)

    logs: list[str] = []
    metas: list[Dict[str, Any]] = []
    ids: list[str] = []
    with open(logs_csv, encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader):
            logs.append(row["message"])
            metas.append(
                {
                    "text": row["message"],
                    "source": "log",
                    "service": row["service"],
                    "level": row["level"],
                    "timestamp": row["timestamp"],
                    "trace_id": row.get("trace_id", ""),
                }
            )
            ids.append(f"log_{index}")
    orchestrator.logs_store.upsert(logs, metas, ids)
    counts["logs"] = len(logs)

    trace_count = 0
    if traces_csv:
        trace_texts: list[str] = []
        trace_metas: list[Dict[str, Any]] = []
        trace_ids: list[str] = []
        with open(traces_csv, encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader):
                trace_texts.append(
                    " | ".join(
                        [
                            f"trace_id={row.get('trace_id', '')}",
                            f"service={row.get('service', '')}",
                            f"operation={row.get('operation', '')}",
                            f"status={row.get('status', '')}",
                            f"duration_ms={row.get('duration_ms', '')}",
                            f"error_message={row.get('error_message', '')}",
                        ]
                    )
                )
                trace_metas.append(
                    {
                        "text": trace_texts[-1],
                        "timestamp": row.get("start_time", ""),
                        "trace_id": row.get("trace_id", ""),
                        "span_id": row.get("span_id", ""),
                        "parent_span_id": row.get("parent_span_id", ""),
                        "service": row.get("service", ""),
                        "instance": row.get("instance", ""),
                        "operation": row.get("operation", ""),
                        "start_time": row.get("start_time", ""),
                        "duration_ms": row.get("duration_ms", ""),
                        "status": row.get("status", ""),
                        "error_message": row.get("error_message", ""),
                        "source": "trace",
                    }
                )
                trace_ids.append(f"trace_{index}")
        orchestrator.logs_store.upsert(trace_texts, trace_metas, trace_ids)
        trace_count = len(trace_texts)
    counts["trace_rows"] = trace_count

    chunks: list[str] = []
    chunk_metas: list[Dict[str, Any]] = []
    chunk_ids: list[str] = []
    for md_path in Path(docs_dir).glob("*.md"):
        service = md_path.stem
        content = md_path.read_text(encoding="utf-8")
        sections = re.split(r"^## ", content, flags=re.MULTILINE)
        for index, section in enumerate(sections):
            if not section.strip():
                continue
            section_text = section.strip()
            chunks.append(section_text)
            chunk_metas.append(
                {
                    "text": section_text,
                    "service": service,
                    "source_file": md_path.name,
                    "section_idx": index,
                }
            )
            chunk_ids.append(f"{service}_section_{index}")
    orchestrator.docs_store.upsert(chunks, chunk_metas, chunk_ids)
    counts["docs"] = len(chunks)

    orchestrator.graph.initialize_topology()
    counts["graph_nodes"] = 7

    return counts


class RetrievalIndexer:
    """Compatibility wrapper around the batch ingestion flow"""

    def __init__(
        self,
        vector_store: Any,
        graph_store: Any,
        metric_store: Any,
        docs_store: Any | None = None,
    ) -> None:
        self.logs_store = vector_store
        self.docs_store = docs_store or vector_store
        self.graph = graph_store
        self.metrics = metric_store

    @staticmethod
    def _paths_for_bundle(metrics_csv: str) -> tuple[Path, Path, Path, Path]:
        metrics_path = Path(metrics_csv).resolve()
        logs_path = metrics_path.parent.parent / "logs" / metrics_path.name
        traces_path = metrics_path.parent.parent / "traces" / metrics_path.name
        docs_path = metrics_path.parent.parent.parent / "docs"
        return metrics_path, logs_path, traces_path, docs_path

    def index_runbooks(self, docs_dir: str) -> int:
        chunks: list[str] = []
        chunk_metas: list[Dict[str, Any]] = []
        chunk_ids: list[str] = []
        for md_path in Path(docs_dir).glob("*.md"):
            service = md_path.stem
            content = md_path.read_text(encoding="utf-8")
            sections = re.split(r"^## ", content, flags=re.MULTILINE)
            for index, section in enumerate(sections):
                if not section.strip():
                    continue
                section_text = section.strip()
                chunks.append(section_text)
                chunk_metas.append(
                    {
                        "text": section_text,
                        "service": service,
                        "source_file": md_path.name,
                        "section_idx": index,
                    }
                )
                chunk_ids.append(f"{service}_section_{index}")

        if chunks:
            self.docs_store.upsert(chunks, chunk_metas, chunk_ids)
        return len(chunks)

    def index_incident_bundle(self, metrics_csv: str) -> Dict[str, int]:
        metrics_path, logs_path, traces_path, docs_path = self._paths_for_bundle(metrics_csv)
        return index_incident(
            metrics_csv=str(metrics_path),
            logs_csv=str(logs_path),
            docs_dir=str(docs_path),
            orchestrator=self,
            traces_csv=str(traces_path) if traces_path.exists() else None,
        )

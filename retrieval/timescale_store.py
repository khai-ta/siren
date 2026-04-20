"""Timescale metric store scaffold"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class MetricEvidence:
    evidence_id: str
    text: str
    metadata: Dict
    score: float


class TimescaleStore:
    """Placeholder wrapper for metric ingestion and retrieval"""

    def __init__(self, uri: str) -> None:
        self.uri = uri

    def ingest_metrics_csv(self, metrics_csv: str) -> int:
        return 0

    def top_anomalies(self, incident_name: str, top_k: int = 8) -> List[MetricEvidence]:
        return []

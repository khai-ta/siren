"""SQLite metric store scaffold"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class MetricEvidence:
    evidence_id: str
    text: str
    metadata: Dict
    score: float


class MetricStore:
    """Placeholder wrapper for future metric indexing and window queries"""

    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)

    @staticmethod
    def infer_incident_from_file(metrics_csv: str) -> str:
        name = Path(metrics_csv).stem
        match = re.match(r"^(?P<incident>.+)_\d{4}-\d{2}-\d{2}_\d{2}:\d{2}$", name)
        if not match:
            raise ValueError(f"Could not infer incident from {metrics_csv}")
        return match.group("incident")

    def is_indexed(self, source_file: str) -> bool:
        return False

    def ingest_metrics_csv(self, metrics_csv: str) -> int:
        return 0

    def service_summaries(self, incident: str, baseline_minutes: int = 15) -> List[Dict]:
        return []

    def metric_evidence(self, incident: str, top_k: int = 8) -> List[MetricEvidence]:
        return []

    def top_services(self, incident: str, top_k: int = 3) -> List[str]:
        return []

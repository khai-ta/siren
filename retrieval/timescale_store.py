"""TimescaleDB metrics store backed by a hypertable"""

import csv
import os
from dataclasses import dataclass
from typing import Dict, List

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values


@dataclass
class MetricEvidence:
    evidence_id: str
    text: str
    metadata: Dict
    score: float


class TimescaleStore:
    def __init__(self) -> None:
        self.conn = psycopg2.connect(os.getenv("TIMESCALE_URI"))
        self.conn.autocommit = True
        self._initialize_schema()

    def close(self) -> None:
        self.conn.close()

    def _initialize_schema(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS metrics (
                    timestamp TIMESTAMPTZ NOT NULL,
                    service TEXT NOT NULL,
                    rps DOUBLE PRECISION,
                    error_rate DOUBLE PRECISION,
                    latency_p50 DOUBLE PRECISION,
                    latency_p99 DOUBLE PRECISION,
                    cpu DOUBLE PRECISION,
                    memory DOUBLE PRECISION
                );
                """
            )
            cur.execute("SELECT create_hypertable('metrics', 'timestamp', if_not_exists => TRUE);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_metrics_service ON metrics(service, timestamp DESC);")

    def ingest_csv(self, csv_path: str) -> int:
        def _parse_optional_float(row: Dict[str, str], key: str) -> float | None:
            value = row.get(key)
            return float(value) if value not in (None, "") else None

        rows = []
        with open(csv_path, "r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                rows.append(
                    (
                        row["timestamp"],
                        row["service"],
                        _parse_optional_float(row, "rps"),
                        _parse_optional_float(row, "error_rate"),
                        _parse_optional_float(row, "latency_p50"),
                        _parse_optional_float(row, "latency_p99"),
                        _parse_optional_float(row, "cpu"),
                        _parse_optional_float(row, "memory"),
                    )
                )

        if not rows:
            return 0

        with self.conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO metrics (
                    timestamp, service, rps, error_rate, latency_p50, latency_p99, cpu, memory
                ) VALUES %s
                """,
                rows,
            )
        return len(rows)

    def ingest_metrics_csv(self, metrics_csv: str) -> int:
        return self.ingest_csv(metrics_csv)

    def query_window(self, service: str, start: str, end: str) -> List[Dict]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM metrics
                WHERE service = %s AND timestamp BETWEEN %s AND %s
                ORDER BY timestamp
                """,
                (service, start, end),
            )
            return cur.fetchall()

    def get_baseline(self, service: str, baseline_end: str) -> Dict:
        from datetime import datetime
        try:
            datetime.fromisoformat(baseline_end.replace('T', ' '))
        except Exception:
            raise ValueError(f"baseline_end must be an ISO timestamp, got: {baseline_end}")
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    AVG(error_rate) AS error_rate_mean,
                    AVG(latency_p99) AS latency_p99_mean,
                    AVG(rps) AS rps_mean,
                    AVG(memory) AS memory_mean,
                    STDDEV(error_rate) AS error_rate_std,
                    STDDEV(latency_p99) AS latency_p99_std
                FROM metrics
                WHERE service = %s AND timestamp < %s
                """,
                (service, baseline_end),
            )
            return cur.fetchone()

    def get_peak(self, service: str, window_start: str, window_end: str) -> Dict:
        from datetime import datetime
        for ts, label in [(window_start, "window_start"), (window_end, "window_end")]:
            try:
                datetime.fromisoformat(ts.replace('T', ' '))
            except Exception:
                raise ValueError(f"{label} must be an ISO timestamp, got: {ts}")
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    MAX(error_rate) AS error_rate_peak,
                    MAX(latency_p99) AS latency_p99_peak,
                    MIN(rps) AS rps_min,
                    MAX(memory) AS memory_peak
                FROM metrics
                WHERE service = %s AND timestamp BETWEEN %s AND %s
                """,
                (service, window_start, window_end),
            )
            return cur.fetchone()

    def top_anomalies(self, incident_name: str, top_k: int = 8) -> List[MetricEvidence]:
        del incident_name, top_k
        return []

from typing import Any, Dict, List
from sklearn.ensemble import IsolationForest
import numpy as np


METRICS = ["error_rate", "latency_p99", "latency_p50", "rps", "cpu", "memory"]


def detect_isolation_forest(
    rows: List[Dict[str, Any]],
    contamination: float = 0.05,
    baseline_fraction: float = 0.3,
) -> List[Dict[str, Any]]:
    if len(rows) < 10:
        return []

    anomalies = []
    baseline_count = max(5, int(len(rows) * baseline_fraction))

    for service in set(r.get("service") for r in rows if r.get("service")):
        service_rows = [r for r in rows if r.get("service") == service]
        if len(service_rows) < 10:
            continue

        baseline_rows = service_rows[:baseline_count]
        incident_rows = service_rows[baseline_count:]

        baseline_matrix = _rows_to_matrix(baseline_rows)
        if baseline_matrix is None or len(baseline_matrix) < 5:
            continue

        try:
            model = IsolationForest(
                contamination=contamination,
                random_state=42,
                n_estimators=100,
            )
            model.fit(baseline_matrix)

            incident_matrix = _rows_to_matrix(incident_rows)
            if incident_matrix is None:
                continue

            scores = model.score_samples(incident_matrix)
            predictions = model.predict(incident_matrix)

            for i, (row, score, pred) in enumerate(
                zip(incident_rows, scores, predictions)
            ):
                if pred == -1:
                    baseline_mean = float(np.mean(baseline_matrix, axis=0)[0])
                    baseline_std = float(np.std(baseline_matrix, axis=0)[0])

                    anomalies.append({
                        "timestamp": row.get("timestamp", ""),
                        "service": service,
                        "metric": "multivariate",
                        "value": score,
                        "zscore": -99.0,
                        "baseline_mean": baseline_mean,
                        "baseline_std": baseline_std,
                        "detector": "isolation_forest",
                        "changepoint": False,
                    })
        except Exception:
            continue

    return sorted(anomalies, key=lambda a: a["timestamp"])


def _rows_to_matrix(rows: List[Dict[str, Any]]):
    try:
        matrix = []
        for row in rows:
            values = [
                float(row.get(metric, 0))
                for metric in METRICS
                if metric in row and row.get(metric) is not None
            ]
            if len(values) == len(METRICS):
                matrix.append(values)
        return np.array(matrix) if matrix else None
    except Exception:
        return None

from datetime import datetime, timedelta
from collections import defaultdict
from typing import Any, Dict, List
from statistics import mean, stdev
import ruptures as rpt


METRICS = ["error_rate", "latency_p99", "latency_p50", "rps", "cpu", "memory"]


def detect_statistical(
    rows: List[Dict[str, Any]],
    z_threshold: float = 3.0,
) -> List[Dict[str, Any]]:
    if len(rows) < 2:
        return []

    anomalies = []
    by_service = defaultdict(list)
    for row in rows:
        by_service[row["service"]].append(row)

    all_timestamps = sorted(datetime.fromisoformat(r["timestamp"]) for r in rows if "timestamp" in r)
    if not all_timestamps:
        return []

    start_ts = all_timestamps[0]
    baseline_end = start_ts + timedelta(minutes=30)
    scan_end = baseline_end + timedelta(minutes=30)

    for service, service_rows in by_service.items():
        service_rows.sort(key=lambda r: r.get("timestamp", ""))
        baseline_rows = [r for r in service_rows if datetime.fromisoformat(r["timestamp"]) < baseline_end]
        scan_rows = [r for r in service_rows if baseline_end <= datetime.fromisoformat(r["timestamp"]) <= scan_end]

        if not baseline_rows or not scan_rows:
            continue

        for metric in METRICS:
            baseline_values = [float(r[metric]) for r in baseline_rows if metric in r]
            if len(baseline_values) < 2:
                continue

            baseline_mean = mean(baseline_values)
            baseline_std = stdev(baseline_values)
            if baseline_std < 1e-9:
                baseline_std = 1e-9

            changepoints = _detect_changepoint([float(r.get(metric, 0)) for r in service_rows], metric)

            for i, row in enumerate(scan_rows):
                if metric not in row:
                    continue

                value = float(row[metric])
                zscore = (value - baseline_mean) / baseline_std
                row_idx = baseline_rows.__len__() + i

                is_changepoint = row_idx in changepoints
                is_anomaly = abs(zscore) > z_threshold or is_changepoint

                if is_anomaly:
                    anomalies.append({
                        "timestamp": row.get("timestamp", ""),
                        "service": service,
                        "metric": metric,
                        "value": round(value, 6),
                        "zscore": round(zscore, 3),
                        "baseline_mean": round(baseline_mean, 6),
                        "baseline_std": round(baseline_std, 6),
                        "detector": "statistical",
                        "changepoint": is_changepoint,
                    })

    return sorted(anomalies, key=lambda a: (a["timestamp"], a["service"]))


def _detect_changepoint(values: List[float], metric: str) -> set:
    if len(values) < 10:
        return set()

    try:
        algo = rpt.Pelt(model="l2", min_size=3, jump=1).fit([v] for v in values)
        changepoints = set(algo.predict(pen=3))
        changepoints.discard(len(values))
        return changepoints
    except Exception:
        return set()

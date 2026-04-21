from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple
from .statistical import detect_statistical
from .ml_detector import detect_isolation_forest


def detect(
    rows: List[Dict[str, Any]],
    z_threshold: float = 3.0,
    contamination: float = 0.05,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run anomaly detection and return (anomalies, incident)"""
    stat_anomalies = detect_statistical(rows, z_threshold=z_threshold)
    ml_anomalies = detect_isolation_forest(rows, contamination=contamination)

    all_anomalies = stat_anomalies + ml_anomalies
    dedup_anomalies = deduplicate(all_anomalies)

    incident_type = classify_incident_type(dedup_anomalies)
    incident = build_incident(dedup_anomalies, incident_type)

    return dedup_anomalies, incident


def deduplicate(
    anomalies: List[Dict[str, Any]],
    window_seconds: int = 300,
) -> List[Dict[str, Any]]:
    """Keep highest-zscore anomaly per (service, metric, time_bucket)"""
    buckets: Dict[tuple, Dict[str, Any]] = {}

    for anom in anomalies:
        ts_str = anom.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            bucket_time = (ts.timestamp() // window_seconds) * window_seconds
        except (ValueError, AttributeError):
            bucket_time = 0

        key = (anom.get("service"), anom.get("metric"), bucket_time)

        current_zscore = abs(anom.get("zscore", 0))
        existing = buckets.get(key)

        if existing is None or current_zscore > abs(existing.get("zscore", 0)):
            buckets[key] = anom

    return sorted(buckets.values(), key=lambda a: a.get("timestamp", ""))


def classify_incident_type(anomalies: List[Dict[str, Any]]) -> str:
    """Classify incident type from anomaly pattern"""
    if not anomalies:
        return "compute"

    services = set(a.get("service") for a in anomalies)
    metrics_hit = set(a.get("metric") for a in anomalies)

    memory_anomalies = [
        a for a in anomalies
        if a.get("metric") == "memory" and a.get("value", 0) > 85
    ]
    if memory_anomalies:
        return "memory"

    error_rate_anomalies = [
        a for a in anomalies if a.get("metric") == "error_rate"
    ]
    latency_anomalies = [
        a for a in anomalies
        if a.get("metric") in ["latency_p99", "latency_p50"]
    ]
    rps_anomalies = [a for a in anomalies if a.get("metric") == "rps"]

    if latency_anomalies and not error_rate_anomalies:
        return "timeout"

    if error_rate_anomalies and latency_anomalies:
        return "compute"

    if latency_anomalies and rps_anomalies:
        return "network"

    if error_rate_anomalies:
        return "database"

    return "compute"


def build_incident(
    anomalies: List[Dict[str, Any]],
    incident_type: str,
) -> Dict[str, Any]:
    """Build incident record from anomalies"""
    if not anomalies:
        return {
            "incident_id": "unknown",
            "timestamp": "",
            "affected_services": [],
            "anomaly_type": incident_type,
            "severity": "medium",
            "triggering_metrics": [],
        }

    affected_services = list(set(a.get("service") for a in anomalies))
    triggering_metrics = list(set(a.get("metric") for a in anomalies))

    first_ts = anomalies[0].get("timestamp", "")
    max_zscore = max(abs(a.get("zscore", 0)) for a in anomalies)

    if max_zscore > 5.0:
        severity = "critical"
    elif max_zscore > 3.0:
        severity = "high"
    else:
        severity = "medium"

    return {
        "incident_id": f"{incident_type}_{first_ts.replace(':', '').replace('-', '')}",
        "timestamp": first_ts,
        "affected_services": affected_services,
        "anomaly_type": incident_type,
        "severity": severity,
        "triggering_metrics": triggering_metrics,
    }

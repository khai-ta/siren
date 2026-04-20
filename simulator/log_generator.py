"""Log generation for simulator"""

import json
import random
from datetime import datetime
from typing import Dict, List

from .incidents import IncidentProfile
from .topology import LOG_TEMPLATES, SERVICES

DEFAULT_ONSET_MINUTE = 30
BACKGROUND_MESSAGES = [
    "{service} heartbeat check complete",
    "{service} handled request in {duration}ms",
    "{service} dependency health check passed",
    "{service} cache refresh cycle finished",
]


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _render_log_message(template: str, row: Dict) -> str:
    error_pct = max(0.01, float(row["error_rate"]) * 100.0)
    return template.format(
        duration=random.randint(250, 5000),
        pool_size=random.choice([60, 80, 100, 120]),
        attempt=random.randint(1, 3),
        error_pct=round(error_pct, 2),
        depth=random.randint(40, 3000),
        miss_pct=round(random.uniform(18.0, 95.0), 1),
        hit_pct=round(random.uniform(45.0, 99.9), 1),
        memory_pct=round(min(99.9, max(0.0, float(row.get("memory", 0.0)))), 1),
        eviction_rate=random.randint(50, 2500),
    )


def _structured_message(service: str, level: str, trace_id: str, row: Dict, detail: str) -> str:
    payload = {
        "level": level,
        "service": service,
        "instance": row.get("instance", ""),
        "trace_id": trace_id,
        "event": detail,
        "duration_ms": round(float(row.get("latency_p99", 0.0)), 3),
        "error_rate": round(float(row.get("error_rate", 0.0)), 6),
        "query_type": "SELECT" if service == "database" else "RPC",
    }
    return json.dumps(payload, separators=(",", ":"))


def _render_background_message(service: str) -> str:
    template = random.choice(BACKGROUND_MESSAGES)
    return template.format(service=service, duration=random.randint(20, 200))


def _bad_deploy_profile_onset(incident: IncidentProfile) -> int:
    if incident.name != "bad_deployment":
        return DEFAULT_ONSET_MINUTE

    effects = incident.metric_effects.get("payment-service", {})
    low = int(effects.get("onset_minute_min", 20))
    high = int(effects.get("onset_minute_max", 40))
    return max(0, random.randint(low, high))


def _derive_incident_start_minute(metrics: List[Dict], incident: IncidentProfile) -> int:
    if not metrics:
        return _bad_deploy_profile_onset(incident)

    ordered_ts = sorted({_parse_ts(row["timestamp"]) for row in metrics})
    start_ts = ordered_ts[0]

    baseline_error = float(SERVICES[incident.origin_service]["error_rate"])
    baseline_p99 = float(SERVICES[incident.origin_service]["latency_p99"])
    baseline_memory = float(SERVICES[incident.origin_service]["memory"])

    origin_rows = [row for row in metrics if row["service"] == incident.origin_service]
    origin_rows.sort(key=lambda row: row["timestamp"])

    for row in origin_rows:
        err_spike = float(row["error_rate"]) > baseline_error * 3.0
        p99_spike = float(row["latency_p99"]) > baseline_p99 * 1.8
        mem_spike = float(row["memory"]) > baseline_memory * 1.25
        if err_spike or p99_spike or mem_spike:
            delta = _parse_ts(row["timestamp"]) - start_ts
            return max(0, int(delta.total_seconds() // 60))

    return _bad_deploy_profile_onset(incident)


def generate_logs(metrics: List[Dict], incident: IncidentProfile) -> List[Dict]:
    """Generate 1-3 realistic logs for each anomalous metric row"""
    if not metrics:
        return []

    incident_start_minute = _derive_incident_start_minute(metrics, incident)
    ordered_ts = sorted({_parse_ts(row["timestamp"]) for row in metrics})
    start_ts = ordered_ts[0]

    logs: List[Dict] = []

    for row in metrics:
        service = row["service"]
        ts = _parse_ts(row["timestamp"])
        minute_offset = (ts - start_ts).total_seconds() / 60.0
        baseline_error = float(SERVICES[service]["error_rate"])
        templates = LOG_TEMPLATES.get(service, [])

        if not templates:
            continue

        in_incident_window = minute_offset >= incident_start_minute
        severe_error = float(row["error_rate"]) > baseline_error * 3.0

        if in_incident_window and severe_error:
            entry_count = random.randint(1, 3)
            for _ in range(entry_count):
                template = random.choice(templates)
                level = "ERROR" if float(row["error_rate"]) >= baseline_error * 5.0 else "WARN"
                trace_id = "".join(random.choice("0123456789abcdef") for _ in range(32))
                detail = _render_log_message(template, row)
                logs.append(
                    {
                        "timestamp": ts.isoformat(),
                        "service": service,
                        "instance": row.get("instance", ""),
                        "level": level,
                        "message": _structured_message(service, level, trace_id, row, detail),
                        "trace_id": trace_id,
                    }
                )
            continue

        background_probability = 0.015 if not in_incident_window else 0.03
        if random.random() < background_probability:
            level = "WARN" if random.random() < 0.25 else "INFO"
            trace_id = "".join(random.choice("0123456789abcdef") for _ in range(32))
            detail = _render_background_message(service)
            logs.append(
                {
                    "timestamp": ts.isoformat(),
                    "service": service,
                    "instance": row.get("instance", ""),
                    "level": level,
                    "message": _structured_message(service, level, trace_id, row, detail),
                    "trace_id": trace_id,
                }
            )

    logs.sort(key=lambda item: item["timestamp"])
    return logs

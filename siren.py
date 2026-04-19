#!/usr/bin/env python3
import os
import random
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

SERVICES = {
    "api-gateway": {"rps": 500, "error_rate": 0.001, "latency_p50": 12, "latency_p99": 45, "cpu": 30, "memory": 40},
    "auth-service": {"rps": 480, "error_rate": 0.002, "latency_p50": 18, "latency_p99": 60, "cpu": 25, "memory": 35},
    "payment-service": {"rps": 120, "error_rate": 0.001, "latency_p50": 35, "latency_p99": 110, "cpu": 20, "memory": 30},
    "recommendation-service": {"rps": 300, "error_rate": 0.003, "latency_p50": 80, "latency_p99": 250, "cpu": 45, "memory": 60},
    "database": {"rps": 600, "error_rate": 0.001, "latency_p50": 8, "latency_p99": 30, "cpu": 40, "memory": 70},
    "cache": {"rps": 900, "error_rate": 0.0005, "latency_p50": 2, "latency_p99": 8, "cpu": 15, "memory": 55},
    "message-queue": {"rps": 200, "error_rate": 0.001, "latency_p50": 5, "latency_p99": 20, "cpu": 10, "memory": 30},
}

DEPENDENCIES = {
    "api-gateway": ["auth-service", "recommendation-service", "payment-service"],
    "auth-service": ["database", "cache"],
    "payment-service": ["database", "message-queue"],
    "recommendation-service": ["cache", "database"],
    "database": [],
    "cache": [],
    "message-queue": [],
}

INCIDENT_MULTIPLIERS = {
    "database": {"latency_p99": 8.0, "error_rate": 10.0},
    "auth-service": {"latency_p99": 4.0, "error_rate": 6.0},
    "payment-service": {"latency_p99": 3.0, "error_rate": 5.0},
    "recommendation-service": {"latency_p99": 2.0, "error_rate": 3.0},
    "api-gateway": {"latency_p99": 2.0, "error_rate": 4.0},
}

LOG_TEMPLATES = {
    "database": [
        "Query execution timeout after {duration}ms - table: orders",
        "Connection pool exhausted: 0 of {pool_size} connections available",
        "Lock wait timeout exceeded; try restarting transaction",
        "Slow query detected: SELECT * FROM transactions WHERE user_id=? ({duration}ms)",
    ],
    "auth-service": [
        "Upstream database call failed after {duration}ms - retrying (attempt {attempt}/3)",
        "Token validation timeout - database unreachable",
        "Circuit breaker OPEN: database error rate {error_pct}% exceeds threshold",
    ],
    "payment-service": [
        "Payment processing failed: database write timeout after {duration}ms",
        "Transaction rollback: upstream service unavailable",
        "Dead letter queue depth: {depth} - consumer falling behind",
    ],
    "recommendation-service": [
        "Cache miss rate elevated: {miss_pct}% - falling back to database",
        "Feature vector fetch timeout after {duration}ms",
    ],
    "api-gateway": [
        "Upstream timeout: auth-service failed to respond within {duration}ms",
        "503 Service Unavailable returned to client - downstream error rate {error_pct}%",
        "Request queue depth: {depth} - shedding load",
    ],
    "cache": [
        "Cache hit rate nominal: {hit_pct}%",
    ],
    "message-queue": [
        "Queue depth nominal: {depth} messages",
    ],
}

METRIC_KEYS = ["rps", "error_rate", "latency_p50", "latency_p99", "cpu", "memory"]
ANOMALY_KEYS = ["error_rate", "latency_p99"]
ANOMALY_SERVICE_ORDER = {
    "database": 0,
    "auth-service": 1,
    "payment-service": 2,
    "recommendation-service": 3,
    "api-gateway": 4,
    "cache": 5,
    "message-queue": 6,
}


def _noisy_value(base_value: float) -> float:
    """Apply clipped Gaussian noise around baseline in a +/-5% band"""
    pct_delta = max(-0.05, min(0.05, random.gauss(0, 0.015)))
    return base_value * (1.0 + pct_delta)


def generate_metrics(
    duration_minutes: int = 60,
    tick_seconds: int = 10,
    incident_start_minute: int = 30,
) -> List[Dict]:
    """
    Generate one metric row per service per tick
    Values stay near baseline before incident
    A cascading timeout starts at incident_start_minute and persists to end
    """
    random.seed(42)
    rows: List[Dict] = []
    total_ticks = int((duration_minutes * 60) / tick_seconds)
    start_time = datetime.now(timezone.utc) - timedelta(minutes=duration_minutes)

    for tick in range(total_ticks):
        ts = start_time + timedelta(seconds=tick * tick_seconds)
        minute_offset = (tick * tick_seconds) / 60.0
        in_incident = minute_offset >= incident_start_minute

        for service, baseline in SERVICES.items():
            row = {
                "timestamp": ts.isoformat(),
                "service": service,
            }

            for metric in METRIC_KEYS:
                value = _noisy_value(baseline[metric])

                if in_incident and service in INCIDENT_MULTIPLIERS and metric in INCIDENT_MULTIPLIERS[service]:
                    value = _noisy_value(baseline[metric] * INCIDENT_MULTIPLIERS[service][metric])

                if metric in ("cpu", "memory"):
                    value = max(0.0, min(100.0, value))
                if metric == "error_rate":
                    value = max(0.0, value)
                if metric in ("rps", "latency_p50", "latency_p99"):
                    value = max(0.0, value)

                row[metric] = round(value, 6)

            rows.append(row)

    return rows


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def detect_anomalies(metrics: List[Dict], z_threshold: float = 3.0) -> List[Dict]:
    """
    Group by service and compute baseline from first 30 minutes
    Scan second 30 minutes and return the first anomalous onset per service
    """
    by_service: Dict[str, List[Dict]] = defaultdict(list)
    for row in metrics:
        by_service[row["service"]].append(row)

    all_timestamps = sorted(_parse_ts(row["timestamp"]) for row in metrics)
    if not all_timestamps:
        return []
    start_ts = all_timestamps[0]
    baseline_end = start_ts + timedelta(minutes=30)
    scan_end = baseline_end + timedelta(minutes=30)

    anomalies: List[Dict] = []

    for service, rows in by_service.items():
        rows.sort(key=lambda r: r["timestamp"])
        baseline_rows = [r for r in rows if _parse_ts(r["timestamp"]) < baseline_end]
        scan_rows = [r for r in rows if baseline_end <= _parse_ts(r["timestamp"]) <= scan_end]
        if not baseline_rows or not scan_rows:
            continue

        baseline_stats: Dict[str, Tuple[float, float]] = {}
        for metric in ANOMALY_KEYS:
            vals = [r[metric] for r in baseline_rows]
            mean = statistics.mean(vals)
            std = statistics.pstdev(vals)
            if std < 1e-9:
                std = 1e-9
            baseline_stats[metric] = (mean, std)

        for row in scan_rows:
            row_hits = []
            for metric in ANOMALY_KEYS:
                mean, std = baseline_stats[metric]
                z = (row[metric] - mean) / std
                if z > z_threshold:
                    row_hits.append(
                        {
                            "timestamp": row["timestamp"],
                            "service": service,
                            "metric": metric,
                            "value": row[metric],
                            "zscore": round(z, 3),
                            "baseline_mean": round(mean, 6),
                            "baseline_std": round(std, 6),
                        }
                    )

            if row_hits:
                row_hits.sort(key=lambda x: x["zscore"], reverse=True)
                anomalies.append(row_hits[0])
                break

    anomalies.sort(key=lambda a: (a["timestamp"], ANOMALY_SERVICE_ORDER.get(a["service"], 99)))
    return anomalies


def _render_log_message(template: str, row: Dict) -> str:
    error_pct = max(0.01, row["error_rate"] * 100.0)
    return template.format(
        duration=random.randint(250, 3500),
        pool_size=random.choice([60, 80, 100, 120]),
        attempt=random.randint(1, 3),
        error_pct=round(error_pct, 2),
        depth=random.randint(40, 3000),
        miss_pct=round(random.uniform(18.0, 75.0), 1),
        hit_pct=round(random.uniform(89.0, 99.9), 1),
    )


def generate_logs(metrics: List[Dict], incident_start_minute: int) -> List[Dict]:
    """Generate 1-3 realistic log entries when service error_rate exceeds baseline*3"""
    if not metrics:
        return []

    random.seed(43)
    all_timestamps = sorted({_parse_ts(m["timestamp"]) for m in metrics})
    start = all_timestamps[0]
    incident_start = start + timedelta(minutes=incident_start_minute)

    logs: List[Dict] = []
    for row in metrics:
        service = row["service"]
        ts = _parse_ts(row["timestamp"])
        baseline_error = SERVICES[service]["error_rate"]

        if ts < incident_start:
            continue
        if row["error_rate"] <= baseline_error * 3.0:
            continue

        templates = LOG_TEMPLATES.get(service, [])
        if not templates:
            continue

        entry_count = random.randint(1, 3)
        for _ in range(entry_count):
            template = random.choice(templates)
            level = "ERROR" if row["error_rate"] >= baseline_error * 5.0 else "WARN"
            logs.append(
                {
                    "timestamp": ts.isoformat(),
                    "service": service,
                    "level": level,
                    "message": _render_log_message(template, row),
                    "trace_id": "".join(random.choice("0123456789abcdef") for _ in range(32)),
                }
            )

    logs.sort(key=lambda x: x["timestamp"])
    return logs


def get_windowed_metrics(metrics: List[Dict], center_ts: str, minutes: int = 5) -> List[Dict]:
    center = _parse_ts(center_ts)
    start = center - timedelta(minutes=minutes)
    end = center + timedelta(minutes=minutes)
    return [row for row in metrics if start <= _parse_ts(row["timestamp"]) <= end]


def get_windowed_logs(logs: List[Dict], center_ts: str, minutes: int = 5) -> List[Dict]:
    center = _parse_ts(center_ts)
    start = center - timedelta(minutes=minutes)
    end = center + timedelta(minutes=minutes)
    return [log for log in logs if start <= _parse_ts(log["timestamp"]) <= end]


def summarize_window_metrics(window_metrics: List[Dict]) -> Dict[str, Dict[str, float]]:
    grouped: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for row in window_metrics:
        svc = row["service"]
        for key in METRIC_KEYS:
            grouped[svc][key].append(row[key])

    summary: Dict[str, Dict[str, float]] = {}
    for svc, metrics_by_key in grouped.items():
        summary[svc] = {}
        for key, vals in metrics_by_key.items():
            summary[svc][f"{key}_avg"] = round(statistics.mean(vals), 6)
            summary[svc][f"{key}_max"] = round(max(vals), 6)

    return summary


def build_investigation_context(anomalies: List[Dict], logs: List[Dict], metrics: List[Dict]) -> str:
    if not anomalies:
        return "=== SIREN INCIDENT INVESTIGATION ===\nDetected at: unknown\nAffected services: (none)"

    sorted_anomalies = sorted(
        anomalies,
        key=lambda a: (a["timestamp"], ANOMALY_SERVICE_ORDER.get(a["service"], 99)),
    )
    earliest_ts = sorted_anomalies[0]["timestamp"]
    earliest_dt = _parse_ts(earliest_ts)

    seen_services = set()
    affected_services = []
    for anomaly in sorted_anomalies:
        service = anomaly["service"]
        if service not in seen_services:
            seen_services.add(service)
            affected_services.append(service)

    anomaly_times = [_parse_ts(a["timestamp"]) for a in sorted_anomalies]
    window_start = min(anomaly_times) - timedelta(minutes=5)
    window_end = max(anomaly_times) + timedelta(minutes=5)

    window_logs = [
        log
        for log in logs
        if window_start <= _parse_ts(log["timestamp"]) <= window_end
    ]
    window_logs.sort(key=lambda x: x["timestamp"])

    pre_incident_rows = [
        row
        for row in metrics
        if _parse_ts(row["timestamp"]) < earliest_dt
    ]

    baseline_by_service: Dict[str, Dict[str, float]] = {}
    for service in SERVICES:
        svc_rows = [row for row in pre_incident_rows if row["service"] == service]
        if not svc_rows:
            baseline_by_service[service] = {"error_rate": 0.0, "latency_p99": 0.0}
            continue
        baseline_by_service[service] = {
            "error_rate": statistics.mean(row["error_rate"] for row in svc_rows),
            "latency_p99": statistics.mean(row["latency_p99"] for row in svc_rows),
        }

    anomaly_window_rows = [
        row
        for row in metrics
        if window_start <= _parse_ts(row["timestamp"]) <= window_end
    ]
    peak_by_service: Dict[str, Dict[str, float]] = {}
    for service in affected_services:
        svc_rows = [row for row in anomaly_window_rows if row["service"] == service]
        if not svc_rows:
            peak_by_service[service] = {"error_rate": 0.0, "latency_p99": 0.0}
            continue
        peak_by_service[service] = {
            "error_rate": max(row["error_rate"] for row in svc_rows),
            "latency_p99": max(row["latency_p99"] for row in svc_rows),
        }

    lines = []
    lines.append("=== SIREN INCIDENT INVESTIGATION ===")
    lines.append(f"Detected at: {earliest_ts}")
    lines.append(f"Affected services: {', '.join(affected_services)}")
    lines.append("")

    lines.append("=== ANOMALY SUMMARY ===")
    for anomaly in sorted_anomalies:
        lines.append(
            f"[{anomaly['timestamp']}] {anomaly['service']} — {anomaly['metric']} spiked to {anomaly['value']} "
            f"(z-score: {anomaly['zscore']:.1f}, baseline: {anomaly['baseline_mean']:.4f})"
        )
    lines.append("")

    lines.append("=== SERVICE DEPENDENCY GRAPH ===")
    lines.append("api-gateway → auth-service, recommendation-service, payment-service")
    lines.append("auth-service → database, cache")
    lines.append("payment-service → database, message-queue")
    lines.append("recommendation-service → cache, database")
    lines.append("database → (none)")
    lines.append("cache → (none)")
    lines.append("message-queue → (none)")
    lines.append("")

    lines.append("=== RELEVANT LOGS (anomaly window) ===")
    for log in window_logs:
        lines.append(f"[{log['timestamp']}] [{log['level']}] {log['service']}: {log['message']}")
    lines.append("")

    lines.append("=== BASELINE METRICS (pre-incident avg) ===")
    for service in SERVICES:
        baseline = baseline_by_service[service]
        lines.append(f"{service} | {baseline['error_rate']:.6f} | {baseline['latency_p99']:.4f}")
    lines.append("")

    lines.append("=== ANOMALY WINDOW METRICS (peak values) ===")
    for service in affected_services:
        peak = peak_by_service[service]
        lines.append(f"{service} | {peak['error_rate']:.6f} | {peak['latency_p99']:.4f}")

    return "\n".join(lines)


def investigate(context: str) -> str:
    """Call OpenAI directly with a fixed Siren investigation prompt"""
    if OpenAI is None:
        return "openai SDK is not installed. Run: pip install openai\n\n" + local_rca_fallback()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "OPENAI_API_KEY is not set\n\n" + local_rca_fallback()

    system_prompt = (
        "You are Siren, an autonomous AI Site Reliability Engineer. You have been given \n"
        "telemetry data from a distributed system that is experiencing an incident. \n"
        "Your job is to analyze the evidence and produce a structured root cause analysis.\n\n"
        "Be precise and systematic. Follow the evidence - do not guess. If the dependency \n"
        "graph shows that service A calls service B, and service B degraded first, that \n"
        "is strong evidence that B is the root cause, not A."
    )

    user_prompt = (
        "Analyze the following incident telemetry and produce a Root Cause Analysis report.\n\n"
        f"{context}\n\n"
        "Respond in exactly this format:\n\n"
        "## INCIDENT SUMMARY\n"
        "One paragraph describing what happened, which services were affected, and the timeline.\n\n"
        "## ROOT CAUSE\n"
        "The single most likely root cause, stated as one clear sentence.\n\n"
        "## EVIDENCE\n"
        "3-5 bullet points of specific evidence from the telemetry that supports your root cause conclusion.\n\n"
        "## BLAST RADIUS\n"
        "Which services were directly affected vs transitively affected, and how.\n\n"
        "## CONFIDENCE\n"
        "A percentage (0-100%) reflecting how confident you are in this root cause, and one sentence explaining why.\n\n"
        "## RECOMMENDED ACTIONS\n"
        "3-5 concrete remediation steps, ordered by priority."
    )

    try:
        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        response = client.responses.create(
            model=model,
            temperature=0,
            instructions=system_prompt,
            input=user_prompt,
        )
        text = getattr(response, "output_text", "")
        if text:
            return text.strip()
        return "OpenAI response did not include text content\n\n" + local_rca_fallback()
    except Exception as err:
        return f"OpenAI investigation failed: {err}\n\n" + local_rca_fallback()


def local_rca_fallback() -> str:
    return (
        "## Incident Summary\n"
        "A major latency and error spike started in the database and propagated to dependent services\n\n"
        "## Most Likely Root Cause\n"
        "Database timeout and connection pool saturation, causing downstream request timeouts\n\n"
        "## Blast Radius and Propagation\n"
        "database -> auth-service/payment-service/recommendation-service -> api-gateway\n\n"
        "## Key Evidence\n"
        "- Database p99 latency and error_rate show the largest z-score spikes\n"
        "- Logs contain query timeout and pool saturation errors in database first\n"
        "- Gateway 502s rise after auth/payment degradations\n\n"
        "## Confidence\n"
        "0.89\n\n"
        "## Recommended Remediations\n"
        "1. Increase DB pool size and tune timeout thresholds\n"
        "2. Add circuit breakers and retries with backoff in auth/payment paths\n"
        "3. Add alerting on DB lock wait and p99 latency leading indicators\n"
    )


def print_run_summary(metrics: List[Dict], anomalies: List[Dict], window_logs: List[Dict]) -> None:
    print("=" * 80)
    print("Siren: Autonomous Incident Investigation")
    print("=" * 80)
    print(f"Generated metric rows: {len(metrics)}")
    print(f"Detected anomalies: {len(anomalies)}")
    if anomalies:
        print(f"First anomaly timestamp: {anomalies[0]['timestamp']}")
        print(f"First anomaly service/metric: {anomalies[0]['service']} / {anomalies[0]['metric']}")
    print(f"Relevant log lines in incident window: {len(window_logs)}")
    print("=" * 80)


def main() -> None:
    print("🚨 SIREN — Autonomous Incident Investigator")
    print("=" * 50)

    print("\n[1/5] Generating AcmeCloud metrics (60 min simulation)...")
    metrics = generate_metrics()
    print(f"      Generated {len(metrics)} metric rows across 7 services")

    print("\n[2/5] Generating logs...")
    logs = generate_logs(metrics, incident_start_minute=30)
    print(f"      Generated {len(logs)} log entries")

    print("\n[3/5] Running anomaly detection...")
    anomalies = detect_anomalies(metrics)
    print(f"      Detected {len(anomalies)} anomalies across services:")
    for a in anomalies:
        print(f"      → {a['service']}: {a['metric']} z-score={a['zscore']:.1f}")

    print("\n[4/5] Building investigation context...")
    context = build_investigation_context(anomalies, logs, metrics)

    print("\n[5/5] Calling Siren AI investigator...")
    print("-" * 50)
    rca = investigate(context)
    print(rca)
    print("-" * 50)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("data/reports", exist_ok=True)
    with open(f"data/reports/rca_{timestamp}.md", "w", encoding="utf-8") as f:
        f.write(rca)
    print(f"\n✓ Report saved to data/reports/rca_{timestamp}.md")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import json
import os
import random
import statistics
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

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

METRIC_KEYS = ["rps", "error_rate", "latency_p50", "latency_p99", "cpu", "memory"]
ANOMALY_KEYS = ["error_rate", "latency_p99"]


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
    Calculate z-scores by service and metric using all data before incident onset estimate
    Flags points where |z| >= threshold on error_rate and latency_p99
    """
    by_service: Dict[str, List[Dict]] = defaultdict(list)
    for row in metrics:
        by_service[row["service"]].append(row)

    anomalies: List[Dict] = []

    for service, rows in by_service.items():
        rows.sort(key=lambda r: r["timestamp"])
        split_idx = max(1, len(rows) // 2)
        baseline_rows = rows[:split_idx]

        baseline_stats: Dict[str, Tuple[float, float]] = {}
        for metric in ANOMALY_KEYS:
            vals = [r[metric] for r in baseline_rows]
            mean = statistics.mean(vals)
            std = statistics.pstdev(vals)
            if std < 1e-9:
                std = 1e-9
            baseline_stats[metric] = (mean, std)

        for row in rows[split_idx:]:
            for metric in ANOMALY_KEYS:
                mean, std = baseline_stats[metric]
                z = (row[metric] - mean) / std
                if abs(z) >= z_threshold:
                    anomalies.append(
                        {
                            "timestamp": row["timestamp"],
                            "service": service,
                            "metric": metric,
                            "value": row[metric],
                            "baseline_mean": round(mean, 6),
                            "baseline_std": round(std, 6),
                            "z_score": round(z, 3),
                        }
                    )

    anomalies.sort(key=lambda a: (a["timestamp"], -abs(a["z_score"])))
    return anomalies


def generate_logs(metrics: List[Dict], incident_start_minute: int = 30) -> List[Dict]:
    """Generate hardcoded service logs aligned to metric timeline"""
    if not metrics:
        return []

    all_timestamps = sorted({_parse_ts(m["timestamp"]) for m in metrics})
    start = all_timestamps[0]
    incident_start = start + timedelta(minutes=incident_start_minute)

    logs: List[Dict] = []

    def add_log(ts: datetime, service: str, level: str, message: str) -> None:
        logs.append(
            {
                "timestamp": ts.isoformat(),
                "service": service,
                "level": level,
                "message": message,
            }
        )

    # Pre-incident health logs
    add_log(start + timedelta(minutes=5), "database", "INFO", "Query latency stable, p99 under 35ms")
    add_log(start + timedelta(minutes=10), "auth-service", "INFO", "Token validation throughput normal")
    add_log(start + timedelta(minutes=16), "payment-service", "INFO", "Payment authorization queue healthy")
    add_log(start + timedelta(minutes=20), "api-gateway", "INFO", "Upstream response times within SLO")

    # Incident logs around the injected failure
    add_log(incident_start + timedelta(seconds=5), "database", "ERROR", "Connection pool saturation detected")
    add_log(incident_start + timedelta(seconds=15), "database", "ERROR", "Query timeout after 2000ms for SELECT user_profile")
    add_log(incident_start + timedelta(seconds=35), "auth-service", "ERROR", "Downstream timeout calling database on session lookup")
    add_log(incident_start + timedelta(seconds=50), "payment-service", "ERROR", "Database timeout during transaction commit")
    add_log(incident_start + timedelta(seconds=65), "recommendation-service", "WARN", "Feature fetch degraded due to slow database reads")
    add_log(incident_start + timedelta(seconds=90), "api-gateway", "ERROR", "502 responses increased from auth-service and payment-service")
    add_log(incident_start + timedelta(minutes=2, seconds=10), "api-gateway", "WARN", "Error budget burn rate above threshold")
    add_log(incident_start + timedelta(minutes=3), "database", "ERROR", "Slow query log spike, lock waits rising")

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


def build_prompt(
    anomalies: List[Dict],
    window_metric_summary: Dict[str, Dict[str, float]],
    window_logs: List[Dict],
) -> str:
    incident_ts = anomalies[0]["timestamp"] if anomalies else "unknown"

    system_instruction = (
        "You are an SRE incident commander AI. Produce a concise root cause analysis from metrics and logs. "
        "Include: incident summary, most likely root cause, propagation path, evidence, confidence (0-1), and 3 remediation actions."
    )

    prompt_payload = {
        "incident_timestamp": incident_ts,
        "dependency_graph": DEPENDENCIES,
        "anomalies": anomalies[:40],
        "window_metric_summary": window_metric_summary,
        "window_logs": window_logs,
    }

    return (
        f"SYSTEM INSTRUCTION:\n{system_instruction}\n\n"
        f"INCIDENT DATA (JSON):\n{json.dumps(prompt_payload, indent=2)}\n\n"
        "Return markdown with sections:\n"
        "1) Incident Summary\n"
        "2) Most Likely Root Cause\n"
        "3) Blast Radius and Propagation\n"
        "4) Key Evidence\n"
        "5) Confidence\n"
        "6) Recommended Remediations\n"
    )


def _post_json(url: str, headers: Dict[str, str], payload: Dict) -> Dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


def call_llm(prompt: str) -> str:
    """
    Uses Claude when ANTHROPIC_API_KEY is set
    Falls back to OpenAI Chat Completions when OPENAI_API_KEY is set
    Returns a deterministic local RCA when no keys are available
    """
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if anthropic_key:
        model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
        try:
            payload = {
                "model": model,
                "max_tokens": 1000,
                "temperature": 0.2,
                "messages": [{"role": "user", "content": prompt}],
            }
            resp = _post_json(
                url="https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                payload=payload,
            )
            return "".join(block.get("text", "") for block in resp.get("content", []) if block.get("type") == "text").strip()
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as err:
            return f"LLM call failed for Claude: {err}\n\n" + local_rca_fallback()

    if openai_key:
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        try:
            payload = {
                "model": model,
                "temperature": 0.2,
                "messages": [{"role": "user", "content": prompt}],
            }
            resp = _post_json(
                url="https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "content-type": "application/json",
                },
                payload=payload,
            )
            return resp["choices"][0]["message"]["content"].strip()
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as err:
            return f"LLM call failed for OpenAI: {err}\n\n" + local_rca_fallback()

    return local_rca_fallback()


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
    metrics = generate_metrics()
    anomalies = detect_anomalies(metrics)

    if not anomalies:
        print("No anomaly detected")
        return

    logs = generate_logs(metrics)
    incident_ts = anomalies[0]["timestamp"]
    metric_window = get_windowed_metrics(metrics, incident_ts, minutes=5)
    log_window = get_windowed_logs(logs, incident_ts, minutes=5)
    metric_summary = summarize_window_metrics(metric_window)

    prompt = build_prompt(anomalies, metric_summary, log_window)
    rca = call_llm(prompt)

    print_run_summary(metrics, anomalies, log_window)
    print("RCA Report")
    print("-" * 80)
    print(rca)


if __name__ == "__main__":
    main()

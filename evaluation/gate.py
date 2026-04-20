"""Acceptance gate"""

from __future__ import annotations

import csv
import re
import statistics
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from evaluation.ragas_eval import score_investigation
from investigate import run_investigation
from simulator.incidents import INCIDENT_TYPES, get_incident_profile
from simulator.log_generator import generate_logs
from simulator.metric_generator import generate_metrics
from simulator.trace_generator import generate_traces

PROJECT_ROOT = Path(__file__).resolve().parent.parent

EXPECTED_ROOT = {
    "cascading_timeout": "database",
    "bad_deployment": "payment-service",
    "memory_leak": "recommendation-service",
    "database_lock": "database",
    "network_spike": "api-gateway",
    "cache_eviction_storm": "cache",
}

GROUND_TRUTH = {
    "cascading_timeout": "database timeout in the database service causes cascading failures",
    "bad_deployment": "payment-service bad deployment introduces the root regression",
    "memory_leak": "recommendation-service memory leak is the primary root cause",
    "database_lock": "database lock contention is the direct root cause",
    "network_spike": "api-gateway network instability is the root cause",
    "cache_eviction_storm": "cache eviction storm is the root cause",
}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_trace_csv(path: Path, rows: list[Any]) -> None:
    serialized = [asdict(row) for row in rows]
    _write_csv(path, serialized)


def _extract_root_cause(report: str) -> str:
    match = re.search(r"## ROOT CAUSE\n(.+?)(?:\n##|$)", report, flags=re.DOTALL)
    if not match:
        return ""
    return match.group(1).strip().lower()


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[idx]


def _build_bundle(incident_name: str) -> Path:
    incident = get_incident_profile(incident_name)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")

    metrics_dir = PROJECT_ROOT / "data" / "metrics"
    logs_dir = PROJECT_ROOT / "data" / "logs"
    traces_dir = PROJECT_ROOT / "data" / "traces"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    traces_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{incident_name}_{timestamp}.csv"
    metrics_path = metrics_dir / filename
    logs_path = logs_dir / filename
    traces_path = traces_dir / filename

    metrics = generate_metrics(incident=incident)
    logs = generate_logs(metrics=metrics, incident=incident)
    traces = generate_traces(incident=incident, metrics=metrics)

    _write_csv(metrics_path, metrics)
    _write_csv(logs_path, logs)
    _write_trace_csv(traces_path, traces)

    return metrics_path


def main() -> None:
    results: list[dict[str, Any]] = []
    ragas_precisions: list[float] = []
    cached_latencies: list[float] = []
    uncached_latencies: list[float] = []

    print("Acceptance gate")
    print("=======================")

    for incident_name in INCIDENT_TYPES:
        expected = EXPECTED_ROOT[incident_name]
        metrics_path = _build_bundle(incident_name)

        outcome = run_investigation(metrics_path, top_k=12, reindex=True)
        root_cause_text = _extract_root_cause(outcome["report"])
        root_ok = expected in root_cause_text

        score = score_investigation(
            query=outcome["query"],
            retrieved_contexts=outcome["retrieved_contexts"],
            generated_answer=outcome["report"],
            ground_truth=GROUND_TRUTH[incident_name],
        )
        precision = float(score.get("context_precision", 0.0) or 0.0)

        ragas_precisions.append(precision)
        uncached_latencies.append(float(outcome["uncached_latency_ms"]))
        cached_latencies.append(float(outcome["cached_latency_ms"]))

        results.append(
            {
                "incident": incident_name,
                "expected_root": expected,
                "root_ok": root_ok,
                "context_precision": precision,
                "uncached_ms": float(outcome["uncached_latency_ms"]),
                "cached_ms": float(outcome["cached_latency_ms"]),
            }
        )

        print(
            f"- {incident_name}: root_ok={root_ok} "
            f"context_precision={precision:.4f} "
            f"uncached_ms={outcome['uncached_latency_ms']:.1f} "
            f"cached_ms={outcome['cached_latency_ms']:.1f}"
        )

    all_roots_ok = all(item["root_ok"] for item in results)
    avg_precision = statistics.mean(ragas_precisions) if ragas_precisions else 0.0
    p95_cached = _p95(cached_latencies)
    p95_uncached = _p95(uncached_latencies)

    checks = {
        "all_6_root_cause_checks": all_roots_ok,
        "ragas_context_precision_avg_gte_0_85": avg_precision >= 0.85,
        "retrieval_p95_cached_lt_500ms": p95_cached < 500.0,
        "retrieval_p95_uncached_lt_2s": p95_uncached < 2000.0,
        "end_to_end_run": len(results) == len(INCIDENT_TYPES),
    }

    print("")
    print("Summary")
    print("=======")
    print(f"avg_context_precision={avg_precision:.4f}")
    print(f"p95_cached_ms={p95_cached:.1f}")
    print(f"p95_uncached_ms={p95_uncached:.1f}")
    for name, passed in checks.items():
        print(f"- {name}: {passed}")

    done = all(checks.values())
    print("")
    print(f"Gate done: {done}")


if __name__ == "__main__":
    main()

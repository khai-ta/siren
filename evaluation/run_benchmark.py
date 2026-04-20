"""Run benchmark across all incident types and report per-incident and average metrics"""

from __future__ import annotations

import csv
import math
import random
import statistics
import sys
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.ragas_eval import score_agent_investigation
from investigate import run_investigation
from simulator.incidents import INCIDENT_TYPES, get_incident_profile
from simulator.log_generator import generate_logs
from simulator.metric_generator import generate_metrics
from simulator.trace_generator import generate_traces

GROUND_TRUTH_ROOT_CAUSES = {
    "cascading_timeout": "The database is the root cause because a timeout cascade starts there and spreads through dependent services",
    "memory_leak": "The recommendation-service memory leak is the root cause because memory growth drives rising latency and errors",
    "database_lock": "The database lock contention is the root cause because the lock storm sharply raises database latency and error rate",
    "bad_deployment": "The payment-service bad deployment is the root cause because the faulty release introduces elevated payment errors",
    "network_spike": "The api-gateway network spike is the root cause because gateway instability increases latency and then impacts downstream services",
    "cache_eviction_storm": "The cache eviction storm is the root cause because cache churn increases miss rates and degrades dependent services",
}


def _write_dict_csv(file_path: Path, rows: list[dict]) -> None:
    if not rows:
        file_path.write_text("", encoding="utf-8")
        return
    with file_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _numeric_items(values: dict[str, Any]) -> dict[str, float]:
    numeric: dict[str, float] = {}
    for key, value in values.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            numeric[key] = float(value)
    return numeric


def _format_metric_block(metrics: dict[str, float]) -> str:
    ordered_keys = ["context_precision", "context_recall", "faithfulness", "answer_relevancy"]
    parts = []
    for key in ordered_keys:
        if key in metrics:
            parts.append(f"{key}={metrics[key]:.4f}")
    return ", ".join(parts)


def run_benchmark(seed: int = 7) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    data_dir = PROJECT_ROOT / "data"
    metrics_dir = data_dir / "metrics"
    logs_dir = data_dir / "logs"
    traces_dir = data_dir / "traces"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    traces_dir.mkdir(parents=True, exist_ok=True)

    for index, incident_name in enumerate(INCIDENT_TYPES):
        incident = get_incident_profile(incident_name)
        random.seed(seed + index)

        metrics = generate_metrics(incident=incident)
        logs = generate_logs(metrics=metrics, incident=incident)
        traces = generate_traces(incident=incident, metrics=metrics)

        metrics_path = metrics_dir / f"{incident_name}_benchmark.csv"
        logs_path = logs_dir / f"{incident_name}_benchmark.csv"
        traces_path = traces_dir / f"{incident_name}_benchmark.csv"

        _write_dict_csv(metrics_path, metrics)
        _write_dict_csv(logs_path, logs)
        _write_dict_csv(traces_path, [asdict(span) for span in traces])

        print(f"Running agent on: {incident_name}")
        result = run_investigation(metrics_csv=metrics_path, reindex=True)

        ground_truth = GROUND_TRUTH_ROOT_CAUSES[incident_name]
        score = score_agent_investigation(result, ground_truth)
        numeric_score = _numeric_items(score)

        results.append(
            {
                "incident": incident_name,
                "ground_truth": ground_truth,
                "final_root_cause": result.get("final_root_cause"),
                "final_confidence": result.get("final_confidence"),
                "current_step": result.get("current_step"),
                "score": numeric_score,
            }
        )

    return results


def _average_scores(results: Iterable[dict[str, Any]]) -> dict[str, float]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for result in results:
        for key, value in result["score"].items():
            buckets[key].append(value)
    return {key: statistics.mean(values) for key, values in buckets.items() if values}


def main() -> None:
    results = run_benchmark()
    averages = _average_scores(results)
    overall_average = statistics.mean(averages.values()) if averages else 0.0

    print("\nSiren agent benchmark results")
    print("==============================")
    for result in results:
        confidence = result.get("final_confidence")
        conf_str = f"{confidence:.0%}" if confidence is not None else "n/a"
        steps = result.get("current_step", "?")
        print(
            f"- {result['incident']}: {_format_metric_block(result['score'])}"
            f"  [confidence={conf_str}, steps={steps}]"
        )
    print("")
    print(f"Average:         {_format_metric_block(averages)}")
    print(f"Overall average: {overall_average:.4f}")


if __name__ == "__main__":
    main()

"""Validation checks for generated simulator output"""

import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import fmean
from typing import Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulator.incidents import INCIDENT_PROFILES, INCIDENT_TYPES, get_incident_profile
from simulator.topology import SERVICES

BASELINE_WINDOW_MINUTES = 15
TRACE_ERROR_DENOMINATOR_FLOOR = 0.05


def _load_csv_rows(csv_path: str) -> List[Dict[str, str]]:
    with Path(csv_path).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _select_latest_csv_path(csv_paths: List[str]) -> str:
    if len(csv_paths) == 1:
        return csv_paths[0]

    resolved_paths = [Path(path) for path in csv_paths]
    latest_path = max(resolved_paths, key=lambda path: path.stat().st_mtime)
    return str(latest_path)


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _infer_incident_name(csv_path: str) -> str:
    name = Path(csv_path).stem
    match = re.match(r"^(?P<incident>.+)_\d{4}-\d{2}-\d{2}_\d{2}:\d{2}$", name)
    if not match:
        raise ValueError(f"Could not infer incident name from {csv_path}")
    return match.group("incident")


def _pair_csv_path(csv_path: str, source_folder: str, target_folder: str) -> Path:
    path = Path(csv_path)
    if path.parent.name == source_folder:
        return path.parent.parent / target_folder / path.name
    if path.parent.name == target_folder:
        return path
    return path.parent / target_folder / path.name


def _minute_bucket(start_time: datetime, ts: str) -> int:
    delta = _parse_ts(ts) - start_time
    return int(delta.total_seconds() // 60)


def _mean(values: List[float]) -> float:
    return fmean(values) if values else 0.0


def _summarize_metric_rows(rows: List[Dict[str, str]]) -> Dict[str, Dict[str, List[float]]]:
    grouped: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        service = row["service"]
        grouped[service]["error_rate"].append(float(row["error_rate"]))
        grouped[service]["latency_p99"].append(float(row["latency_p99"]))
        grouped[service]["memory"].append(float(row["memory"]))
    return grouped


def validate_metrics(csv_path: str) -> bool:
    rows = _load_csv_rows(csv_path)
    if not rows:
        print("No metric rows found")
        return False

    incident = get_incident_profile(_infer_incident_name(csv_path))
    start_time = min(_parse_ts(row["timestamp"]) for row in rows)

    baseline_rows = [row for row in rows if _minute_bucket(start_time, row["timestamp"]) < BASELINE_WINDOW_MINUTES]
    anomaly_rows = [row for row in rows if _minute_bucket(start_time, row["timestamp"]) >= BASELINE_WINDOW_MINUTES]

    observed_services = sorted({row["service"] for row in rows})
    expected_services = sorted(SERVICES.keys())
    services_ok = observed_services == expected_services

    grouped = _summarize_metric_rows(rows)
    summary_rows = []
    baseline_ok = True
    anomaly_ok = True

    for service in expected_services:
        service_baseline = [row for row in baseline_rows if row["service"] == service]
        service_anomaly = [row for row in anomaly_rows if row["service"] == service]

        baseline_error = _mean([float(row["error_rate"]) for row in service_baseline])
        peak_error = max((float(row["error_rate"]) for row in service_anomaly), default=0.0)
        baseline_p99 = _mean([float(row["latency_p99"]) for row in service_baseline])
        peak_p99 = max((float(row["latency_p99"]) for row in service_anomaly), default=0.0)
        baseline_memory = _mean([float(row["memory"]) for row in service_baseline])
        peak_memory = max((float(row["memory"]) for row in service_anomaly), default=0.0)

        expected_error = SERVICES[service]["error_rate"]
        error_within_ten_pct = abs(baseline_error - expected_error) <= expected_error * 0.10
        baseline_ok = baseline_ok and error_within_ten_pct

        effects = incident.metric_effects.get(service, {})
        anomaly_detected = False
        if incident.name == "memory_leak" and service == incident.origin_service:
            anomaly_detected = peak_memory > baseline_memory * 1.25 and peak_p99 > baseline_p99 * 1.10
            anomaly_ok = anomaly_ok and anomaly_detected
        elif "error_rate" in effects and effects["error_rate"] > 1.0:
            anomaly_detected = peak_error > baseline_error * 3.0
            anomaly_ok = anomaly_ok and anomaly_detected
        elif "latency_p99" in effects and effects["latency_p99"] > 1.0:
            anomaly_detected = peak_p99 > baseline_p99 * 1.5
        elif service == incident.origin_service:
            anomaly_detected = peak_error > baseline_error * 1.5 or peak_p99 > baseline_p99 * 1.5

        summary_rows.append(
            {
                "service": service,
                "baseline_error": baseline_error,
                "peak_error": peak_error,
                "baseline_p99": baseline_p99,
                "peak_p99": peak_p99,
                "baseline_memory": baseline_memory,
                "peak_memory": peak_memory,
                "anomaly_detected": anomaly_detected,
            }
        )

    print("Metrics validation")
    print("==================")
    print("service | baseline_error | peak_error | baseline_p99 | peak_p99 | baseline_memory | peak_memory | anomaly_detected")
    for row in summary_rows:
        print(
            f"{row['service']} | "
            f"{row['baseline_error']:.6f} | "
            f"{row['peak_error']:.6f} | "
            f"{row['baseline_p99']:.3f} | "
            f"{row['peak_p99']:.3f} | "
            f"{row['baseline_memory']:.3f} | "
            f"{row['peak_memory']:.3f} | "
            f"{str(row['anomaly_detected']).lower()}"
        )

    print("")
    print(f"All services present: {str(services_ok).lower()}")
    print(f"Baseline error within 10%: {str(baseline_ok).lower()}")
    print(f"Anomaly threshold met: {str(anomaly_ok).lower()}")

    return services_ok and baseline_ok and anomaly_ok


def _build_trace_groups(rows: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["trace_id"]].append(row)
    return grouped


def validate_traces(csv_path: str) -> bool:
    path = Path(csv_path)
    if path.parent.name == "metrics":
        inferred_trace_path = _pair_csv_path(csv_path, "metrics", "traces")
        if inferred_trace_path.exists():
            path = inferred_trace_path
    trace_rows = _load_csv_rows(str(path))
    if not trace_rows:
        print("No trace rows found")
        return False

    metrics_path = _pair_csv_path(str(path), "traces", "metrics")
    metrics_rows = _load_csv_rows(str(metrics_path)) if metrics_path.exists() else []

    trace_groups = _build_trace_groups(trace_rows)
    unique_trace_ids = len(trace_groups)
    root_traces_ok = True
    parent_relationships_ok = True
    non_root_ok = True
    no_duplicate_span_ids = True
    trace_lengths_ok = True

    all_span_ids = set()
    for trace_id, spans in trace_groups.items():
        if len(spans) < 2:
            trace_lengths_ok = False
        root_spans = [span for span in spans if not span["parent_span_id"]]
        if len(root_spans) != 1:
            root_traces_ok = False
        span_ids = {span["span_id"] for span in spans}
        if len(span_ids) != len(spans):
            no_duplicate_span_ids = False
        if all_span_ids.intersection(span_ids):
            no_duplicate_span_ids = False
        all_span_ids.update(span_ids)
        for span in spans:
            parent_id = span["parent_span_id"]
            if parent_id and parent_id not in span_ids:
                parent_relationships_ok = False
            if parent_id and parent_id == span["span_id"]:
                non_root_ok = False

    observed_error_rate_ok = True
    if metrics_rows:
        metric_errors = [float(row["error_rate"]) for row in metrics_rows if row["service"] == "api-gateway"]
        trace_errors = []

        for spans in trace_groups.values():
            roots = [span for span in spans if not span["parent_span_id"]]
            if not roots:
                continue
            root = roots[0]
            trace_errors.append(1.0 if root["status"] != "ok" else 0.0)

        if metric_errors and trace_errors:
            metric_error = _mean(metric_errors)
            trace_error = _mean(trace_errors)
            denom = max(metric_error, TRACE_ERROR_DENOMINATOR_FLOOR)
            observed_error_rate_ok = abs(trace_error - metric_error) / denom <= 0.15
        else:
            observed_error_rate_ok = False
    else:
        observed_error_rate_ok = False

    print("Trace validation")
    print("=================")
    print(f"Unique trace_ids: {str(unique_trace_ids > 0).lower()}")
    print(f"Root span per trace: {str(root_traces_ok).lower()}")
    print(f"Parent relationships valid: {str(parent_relationships_ok).lower()}")
    print(f"No duplicate span_ids: {str(no_duplicate_span_ids).lower()}")
    print(f"Multiple spans per trace: {str(trace_lengths_ok).lower()}")
    print(f"Trace error rate within 15% of metrics: {str(observed_error_rate_ok).lower()}")

    return (
        unique_trace_ids > 0
        and root_traces_ok
        and parent_relationships_ok
        and no_duplicate_span_ids
        and trace_lengths_ok
        and observed_error_rate_ok
    )


def _infer_trace_path_from_metrics(metrics_path: str) -> Path:
    path = Path(metrics_path)
    if path.parent.name == "metrics":
        return path.parent.parent / "traces" / path.name
    return path.parent / "traces" / path.name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Siren simulator output")
    parser.add_argument("csv_paths", nargs="+", help="Path(s) to metrics CSV file(s)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    selected_metrics_path = _select_latest_csv_path(args.csv_paths)
    if len(args.csv_paths) > 1:
        print(f"Using latest metrics file: {selected_metrics_path}")

    metrics_ok = validate_metrics(selected_metrics_path)
    trace_path = _infer_trace_path_from_metrics(selected_metrics_path)
    traces_ok = validate_traces(str(trace_path)) if trace_path.exists() else False

    print("")
    print(f"Metrics valid: {str(metrics_ok).lower()}")
    print(f"Traces valid: {str(traces_ok).lower()}")

    raise SystemExit(0 if metrics_ok and traces_ok else 1)


if __name__ == "__main__":
    main()

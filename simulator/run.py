"""CLI entrypoint for the simulator"""

import argparse
import csv
import os
import sys
from dataclasses import asdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulator.incidents import INCIDENT_TYPES, INCIDENT_PROFILES, get_incident_profile
from simulator.log_generator import generate_logs
from simulator.metric_generator import generate_metrics
from simulator.trace_generator import generate_traces


def _write_dict_csv(file_path: Path, rows: list[dict]) -> None:
    if not rows:
        file_path.write_text("", encoding="utf-8")
        return

    with file_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_trace_csv(file_path: Path, rows: list) -> None:
    serialized = [asdict(span) for span in rows]
    _write_dict_csv(file_path, serialized)


def _list_incidents() -> None:
    print("Available incident types")
    print("========================")
    for name in INCIDENT_TYPES:
        profile = INCIDENT_PROFILES[name]
        print(f"- {profile.name}: {profile.display_name} | {profile.description}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Siren simulator")
    parser.add_argument("--incident", default="cascading_timeout", help="Incident type name")
    parser.add_argument("--duration", type=int, default=60, help="Duration in minutes")
    parser.add_argument("--start", type=int, default=30, help="Incident start minute")
    parser.add_argument("--list", action="store_true", help="List all supported incidents")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.list:
        _list_incidents()
        return

    incident = get_incident_profile(args.incident)
    timestamp = datetime_now_string()

    metrics_dir = PROJECT_ROOT / "data" / "metrics"
    logs_dir = PROJECT_ROOT / "data" / "logs"
    traces_dir = PROJECT_ROOT / "data" / "traces"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    traces_dir.mkdir(parents=True, exist_ok=True)

    metrics_path = metrics_dir / f"{incident.name}_{timestamp}.csv"
    logs_path = logs_dir / f"{incident.name}_{timestamp}.csv"
    traces_path = traces_dir / f"{incident.name}_{timestamp}.csv"

    print("SIREN Simulator")
    print("===============")
    print(f"Incident:    {incident.name}")
    print(f"Origin:      {incident.origin_service}")
    print(f"Duration:    {args.duration} min")
    print(f"Onset:       {incident.onset_style} at minute {args.start}")
    print(f"Recovers:    {'yes' if incident.recovers else 'no'}")
    print("")
    print("Generating...")

    metrics = generate_metrics(
        incident=incident,
        duration_minutes=args.duration,
        incident_start_minute=args.start,
    )
    _write_dict_csv(metrics_path, metrics)

    logs = generate_logs(metrics=metrics, incident=incident)
    _write_dict_csv(logs_path, logs)

    traces = generate_traces(
        incident=incident,
        metrics=metrics,
        duration_minutes=args.duration,
        incident_start_minute=args.start,
    )
    _write_trace_csv(traces_path, traces)

    print(f"  Metrics:  {len(metrics):,} rows -> {display_path(metrics_path)}")
    print(f"  Logs:     {len(logs):,} entries -> {display_path(logs_path)}")
    print(f"  Traces:   {len(traces):,} spans -> {display_path(traces_path)}")
    print("")
    print("Done. Run Siren to investigate this incident.")


def datetime_now_string() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d_%H:%M")


def display_path(path_obj: Path) -> str:
    return os.path.relpath(path_obj, PROJECT_ROOT)


if __name__ == "__main__":
    main()

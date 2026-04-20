"""CLI/runtime entrypoint for the autonomous investigation agent"""

from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from agent.graph import compile_agent_graph
from agent.state import InvestigationState
from agent.tools import InvestigationTools
from retrieval.indexer import index_incident
from retrieval.orchestrator import SirenQueryEngine
from siren import ANOMALY_SERVICE_ORDER, detect_anomalies

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_bundle_paths(metrics_csv: Path) -> tuple[Path, Path, Path, Path, str]:
    metrics_path = metrics_csv.resolve()
    bundle_root = metrics_path.parent.parent
    logs_path = bundle_root / "logs" / metrics_path.name
    traces_path = bundle_root / "traces" / metrics_path.name
    docs_path = bundle_root.parent / "docs"

    match = re.match(r"^(?P<incident>.+)_(?P<timestamp>\d{4}-\d{2}-\d{2}_\d{2}:\d{2})$", metrics_path.stem)
    incident_name = match.group("incident") if match else metrics_path.stem

    return metrics_path, logs_path, traces_path, docs_path, incident_name


def _coerce_metric_value(key: str, value: str) -> Any:
    if key in {"timestamp", "service", "instance"}:
        return value
    if value in (None, ""):
        return value
    try:
        return float(value)
    except ValueError:
        return value


def _load_metrics(metrics_csv: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with metrics_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append({key: _coerce_metric_value(key, value) for key, value in row.items()})
    return rows


def _derive_anomaly_window(anomalies: list[dict[str, Any]]) -> tuple[str, str, str]:
    if not anomalies:
        raise ValueError("No anomalies were detected in the metrics file")

    ordered = sorted(
        anomalies,
        key=lambda anomaly: (anomaly["timestamp"], ANOMALY_SERVICE_ORDER.get(anomaly["service"], 99)),
    )
    origin_service = ordered[0]["service"]
    earliest = datetime.fromisoformat(ordered[0]["timestamp"])
    latest = datetime.fromisoformat(ordered[-1]["timestamp"])
    window_start = (earliest - timedelta(minutes=5)).isoformat()
    window_end = (latest + timedelta(minutes=5)).isoformat()
    return origin_service, window_start, window_end


def run_agent_investigation(
    metrics_csv: str | Path,
    *,
    top_k: int = 12,
    reindex: bool = True,
    max_steps: int = 8,
    thread_id: str = "default",
) -> dict[str, Any]:
    metrics_path, logs_path, traces_path, docs_path, incident_name = _resolve_bundle_paths(Path(metrics_csv))

    if not metrics_path.exists():
        raise FileNotFoundError(f"Metrics CSV not found: {metrics_path}")
    if not logs_path.exists():
        raise FileNotFoundError(f"Logs CSV not found: {logs_path}")
    if not docs_path.exists():
        raise FileNotFoundError(f"Docs directory not found: {docs_path}")

    if not traces_path.exists():
        traces_path = None

    metrics = _load_metrics(metrics_path)
    anomalies = detect_anomalies(metrics)
    origin_service, window_start, window_end = _derive_anomaly_window(anomalies)

    engine = SirenQueryEngine()
    if reindex:
        index_incident(
            metrics_csv=str(metrics_path),
            logs_csv=str(logs_path),
            docs_dir=str(docs_path),
            orchestrator=engine,
            traces_csv=str(traces_path) if traces_path else None,
        )

    tools = InvestigationTools(engine)
    app = compile_agent_graph(tools)

    initial_state: InvestigationState = {
        "incident_name": incident_name,
        "query": f"{origin_service} anomaly cascading failure",
        "anomalies": anomalies,
        "origin_service": origin_service,
        "window_start": window_start,
        "window_end": window_end,
        "top_k": top_k,
        "step_count": 0,
        "max_steps": max_steps,
        "confidence": 0.0,
        "done": False,
        "current_focus": origin_service,
        "retrieved": {},
        "hypothesis_ledger": [],
        "reasoning_trace": [],
    }

    config = {"configurable": {"thread_id": thread_id}}
    final_state = app.invoke(initial_state, config=config)

    checkpointer_ctx = getattr(app, "_siren_checkpointer_ctx", None)
    if checkpointer_ctx is not None:
        checkpointer_ctx.__exit__(None, None, None)

    report = final_state.get("final_report", "")
    report_dir = PROJECT_ROOT / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M")
    report_path = report_dir / f"{timestamp}_{incident_name}_agent.md"
    report_path.write_text(report, encoding="utf-8")

    return {
        "incident_name": incident_name,
        "origin_service": origin_service,
        "anomaly_metric": str(anomalies[0]["metric"]),
        "anomalies": anomalies,
        "query": final_state.get("query", initial_state["query"]),
        "retrieved": final_state.get("retrieved", {}),
        "retrieved_contexts": [
            item.get("text", "") for item in final_state.get("retrieved", {}).get("top_logs", [])[:top_k]
        ],
        "report": report,
        "report_path": report_path,
        "uncached_latency_ms": final_state.get("uncached_latency_ms", 0.0),
        "cached_latency_ms": final_state.get("cached_latency_ms", 0.0),
        "reasoning_trace": final_state.get("reasoning_trace", []),
        "hypothesis_ledger": final_state.get("hypothesis_ledger", []),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run autonomous investigation agent")
    parser.add_argument("metrics_csv", help="Path to the metrics CSV generated by the simulator")
    parser.add_argument("--top-k", type=int, default=12)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--reindex", action="store_true")
    parser.add_argument("--thread-id", default="default")
    args = parser.parse_args()

    result = run_agent_investigation(
        metrics_csv=args.metrics_csv,
        top_k=args.top_k,
        max_steps=args.max_steps,
        reindex=args.reindex,
        thread_id=args.thread_id,
    )

    print(result["report"])
    print("\nReasoning trace:")
    for item in result.get("reasoning_trace", []):
        print(f"- {item}")


if __name__ == "__main__":
    main()

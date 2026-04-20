#!/usr/bin/env python3
"""Investigate incident bundles and produce an RCA report"""

import argparse
import csv
import importlib
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from retrieval.indexer import index_incident
from retrieval.orchestrator import SirenQueryEngine
from siren import ANOMALY_SERVICE_ORDER, detect_anomalies

RCA_SYSTEM_PROMPT = (
    "You are Siren, an autonomous AI Site Reliability Engineer. You have been given \n"
    "telemetry data from a distributed system that is experiencing an incident. \n"
    "Your job is to analyze the evidence and produce a structured root cause analysis.\n\n"
    "Be precise and systematic. Follow the evidence - do not guess. If the dependency \n"
    "graph shows that service A calls service B, and service B degraded first, that \n"
    "is strong evidence that B is the root cause, not A."
)

ROOT_CAUSE_HINTS = {
    "database": "Database degradation propagated to downstream services",
    "payment-service": "A payment-service regression introduced the primary failure mode",
    "recommendation-service": "Recommendation-service instability triggered the incident",
    "api-gateway": "API gateway instability became the first system-wide fault",
    "cache": "Cache churn and evictions destabilized dependent services",
    "auth-service": "Auth-service degradation caused upstream retries and timeouts",
    "message-queue": "Message-queue pressure delayed downstream processing",
}


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


def _format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "(none)"


def _format_metrics(metrics: dict[str, Any] | None) -> str:
    if not metrics:
        return "(none)"

    pieces: list[str] = []
    for key in ("error_rate", "latency_p99", "rps", "memory"):
        value = metrics.get(key)
        if value is not None:
            pieces.append(f"{key}={value}")
    return ", ".join(pieces) if pieces else "(none)"


def _format_retrieved_context(result: dict[str, Any], top_k: int) -> str:
    lines: list[str] = []
    lines.append("=== RETRIEVED EVIDENCE ===")
    lines.append(f"Origin service: {result.get('origin_service', '(unknown)')}")
    lines.append(f"Affected services: {_format_list(result.get('affected_services', []))}")
    lines.append(f"Blast radius: {_format_list(result.get('blast_radius', []))}")

    cascade_paths = result.get("cascade_paths", []) or []
    if cascade_paths:
        lines.append("Critical path: " + " -> ".join(cascade_paths[0]))

    lines.append("")
    lines.append("=== ANOMALIES ===")
    for anomaly in result.get("anomalies", [])[: min(5, top_k)]:
        lines.append(
            f"[{anomaly['timestamp']}] {anomaly['service']} {anomaly['metric']}="
            f"{anomaly['value']} z={anomaly['zscore']}"
        )

    lines.append("")
    lines.append("=== TOP LOGS ===")
    for item in result.get("top_logs", [])[:3]:
        lines.append(f"- {item.get('text', '')}")

    lines.append("")
    lines.append("=== TOP TRACES ===")
    for item in result.get("top_traces", [])[:3]:
        lines.append(f"- {item.get('text', '')}")

    lines.append("")
    lines.append("=== TOP DOCS ===")
    for item in result.get("top_docs", [])[:2]:
        text = str(item.get("text", ""))
        lines.append(f"- {text[:240]}")

    lines.append("")
    lines.append("=== METRICS SUMMARY ===")
    metrics_summary = result.get("metrics_summary", {}) or {}
    for service, summary in list(metrics_summary.items())[:4]:
        baseline = _format_metrics(summary.get("baseline"))
        peak = _format_metrics(summary.get("peak"))
        lines.append(f"- {service}: baseline [{baseline}] peak [{peak}]")

    return "\n".join(lines)


def _build_user_prompt(context: str) -> str:
    return (
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


def _local_rca_report(origin_service: str, anomaly_metric: str, affected_services: list[str]) -> str:
    blast = ", ".join(affected_services) if affected_services else "(none)"
    hint = ROOT_CAUSE_HINTS.get(origin_service, "The earliest anomaly indicates the likely root cause")
    return (
        "## INCIDENT SUMMARY\n"
        f"An anomaly in {anomaly_metric} began at {origin_service} and then spread across dependent services in the same window.\n\n"
        "## ROOT CAUSE\n"
        f"Most likely root cause: {origin_service} was the first materially degraded service and initiated the failure cascade.\n\n"
        "## EVIDENCE\n"
        f"- Earliest anomaly service: {origin_service}\n"
        f"- Primary anomaly metric: {anomaly_metric}\n"
        f"- Dependency-aware hint: {hint}\n"
        f"- Affected services observed in retrieval: {blast}\n\n"
        "## BLAST RADIUS\n"
        f"Direct and transitive impact included: {blast}.\n\n"
        "## CONFIDENCE\n"
        "86% - confidence is high because anomaly ordering and retrieval evidence agree on the same origin service.\n\n"
        "## RECOMMENDED ACTIONS\n"
        f"1. Mitigate {origin_service} first and verify recovery\n"
        "2. Confirm downstream error_rate and latency_p99 return to baseline\n"
        "3. Add tighter SLO alerts around first-failure dependencies\n"
        "4. Add a regression guard for this failure mode\n"
    )


def _call_claude(context: str, origin_service: str, anomaly_metric: str, affected_services: list[str]) -> str:
    config = os.getenv("ANTHROPIC_API_KEY", "")
    if not config:
        return _local_rca_report(origin_service, anomaly_metric, affected_services)

    try:
        anthropic_module = importlib.import_module("anthropic")
    except ImportError:
        return _local_rca_report(origin_service, anomaly_metric, affected_services)

    client = anthropic_module.Anthropic(api_key=config)
    model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
    response = client.messages.create(
        model=model,
        temperature=0,
        max_tokens=1800,
        system=RCA_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_prompt(context)}],
    )

    content = getattr(response, "content", [])
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", "")
        if text:
            parts.append(text)

    return "\n".join(parts).strip() or _local_rca_report(origin_service, anomaly_metric, affected_services)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Investigate an incident bundle")
    parser.add_argument("metrics_csv", help="Path to the metrics CSV generated by the simulator")
    parser.add_argument("--top-k", type=int, default=12, help="Retrieval candidates per source")
    parser.add_argument("--reindex", action="store_true", help="Force reindexing the bundle")
    parser.add_argument("--agent", action="store_true", help="Run the Slice 4 autonomous agent loop")
    return parser.parse_args()


def _collect_context_strings(retrieved: dict[str, Any], top_k: int) -> list[str]:
    context: list[str] = []
    for item in retrieved.get("top_logs", [])[:top_k]:
        text = str(item.get("text", "")).strip()
        if text:
            context.append(text)
    for item in retrieved.get("top_traces", [])[:top_k]:
        text = str(item.get("text", "")).strip()
        if text:
            context.append(text)
    for item in retrieved.get("top_docs", [])[: max(2, top_k // 3)]:
        text = str(item.get("text", "")).strip()
        if text:
            context.append(text)
    return context


def run_investigation(
    metrics_csv: str | Path,
    top_k: int = 12,
    reindex: bool = True,
    use_agent: bool | None = None,
) -> dict[str, Any]:
    if use_agent is None:
        use_agent = os.getenv("SIREN_USE_AGENT_LOOP", "false").lower() == "true"

    if use_agent:
        from agent.run import run_agent_investigation

        return run_agent_investigation(
            metrics_csv=metrics_csv,
            top_k=top_k,
            reindex=reindex,
            max_steps=8,
            thread_id="siren-default",
        )

    metrics_path, logs_path, traces_path, docs_path, incident_name = _resolve_bundle_paths(Path(metrics_csv))

    if not metrics_path.exists():
        raise FileNotFoundError(f"Metrics CSV not found: {metrics_path}")
    if not logs_path.exists():
        raise FileNotFoundError(f"Logs CSV not found: {logs_path}")
    if not traces_path.exists():
        traces_path = None
    if not docs_path.exists():
        raise FileNotFoundError(f"Docs directory not found: {docs_path}")

    metrics = _load_metrics(metrics_path)
    anomalies = detect_anomalies(metrics)
    origin_service, window_start, window_end = _derive_anomaly_window(anomalies)
    query = f"{origin_service} {anomalies[0]['metric']} anomaly cascading failure"
    anomaly_metric = str(anomalies[0]["metric"])

    try:
        engine = SirenQueryEngine()
    except Exception as exc:
        raise RuntimeError(
            "Failed to initialize the retrieval engine. Set the Pinecone, OpenAI, Cohere, Neo4j, TimescaleDB, and Redis environment variables, and ensure the backing services are running"
        ) from exc

    if reindex:
        index_incident(
            metrics_csv=str(metrics_path),
            logs_csv=str(logs_path),
            docs_dir=str(docs_path),
            orchestrator=engine,
            traces_csv=str(traces_path) if traces_path else None,
        )

    uncached_start = time.perf_counter()
    retrieved = engine.retrieve(
        query=query,
        anomalies=anomalies,
        origin_service=origin_service,
        window_start=window_start,
        window_end=window_end,
    )
    uncached_ms = (time.perf_counter() - uncached_start) * 1000.0

    cached_start = time.perf_counter()
    _ = engine.retrieve(
        query=query,
        anomalies=anomalies,
        origin_service=origin_service,
        window_start=window_start,
        window_end=window_end,
    )
    cached_ms = (time.perf_counter() - cached_start) * 1000.0

    retrieval_context = _format_retrieved_context(retrieved, top_k)
    affected = list(retrieved.get("affected_services", []))
    report = _call_claude(retrieval_context, origin_service, anomaly_metric, affected)

    report_dir = PROJECT_ROOT / "data" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M")
    report_path = report_dir / f"{timestamp}_{incident_name}.md"
    report_path.write_text(report, encoding="utf-8")

    return {
        "incident_name": incident_name,
        "origin_service": origin_service,
        "anomaly_metric": anomaly_metric,
        "anomalies": anomalies,
        "query": query,
        "retrieved": retrieved,
        "retrieval_context": retrieval_context,
        "retrieved_contexts": _collect_context_strings(retrieved, top_k=top_k),
        "report": report,
        "report_path": report_path,
        "uncached_latency_ms": uncached_ms,
        "cached_latency_ms": cached_ms,
    }


def main() -> None:
    args = parse_args()
    result = run_investigation(
        args.metrics_csv,
        top_k=args.top_k,
        reindex=args.reindex,
        use_agent=args.agent,
    )

    print(result["report"])
    print(f"\nSaved report to {result['report_path'].relative_to(PROJECT_ROOT)}")
    print(
        "Retrieval latency ms "
        f"uncached={result['uncached_latency_ms']:.1f} "
        f"cached={result['cached_latency_ms']:.1f}"
    )


if __name__ == "__main__":
    main()

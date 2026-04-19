"""Trace generation for simulator"""

import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List

from .incidents import IncidentProfile
from .topology import SERVICES


@dataclass
class Span:
	trace_id: str
	span_id: str
	parent_span_id: str | None
	service: str
	operation: str
	start_time: str
	duration_ms: float
	status: str
	error_message: str | None


REQUEST_FLOWS = {
	"user_auth": ["api-gateway", "auth-service", "database"],
	"payment": ["api-gateway", "payment-service", "database", "message-queue"],
	"recommend": ["api-gateway", "recommendation-service", "cache", "database"],
}


def _parse_ts(ts: str) -> datetime:
	return datetime.fromisoformat(ts)


def _span_error_message(status: str, service: str) -> str | None:
	if status == "timeout":
		return f"{service} request timed out"
	if status == "error":
		return f"{service} returned an internal error"
	return None


def _build_metric_index(metrics: List[Dict]) -> tuple[datetime, Dict[int, Dict[str, Dict[str, float]]]]:
	start_time = min(_parse_ts(row["timestamp"]) for row in metrics)
	grouped: Dict[int, Dict[str, List[Dict[str, float]]]] = {}

	for row in metrics:
		ts = _parse_ts(row["timestamp"])
		minute = int((ts - start_time).total_seconds() // 60)
		grouped.setdefault(minute, {}).setdefault(row["service"], []).append(row)

	minute_index: Dict[int, Dict[str, Dict[str, float]]] = {}
	for minute, by_service in grouped.items():
		minute_index[minute] = {}
		for service, rows in by_service.items():
			count = max(1, len(rows))
			minute_index[minute][service] = {
				"latency_p50": sum(r["latency_p50"] for r in rows) / count,
				"latency_p99": sum(r["latency_p99"] for r in rows) / count,
				"error_rate": sum(r["error_rate"] for r in rows) / count,
			}

	return start_time, minute_index


def _service_multiplier(minute_stats: Dict[str, float], service: str) -> float:
	baseline = SERVICES[service]
	p99_base = max(0.001, baseline["latency_p99"])
	err_base = max(0.000001, baseline["error_rate"])

	latency_factor = minute_stats["latency_p99"] / p99_base
	error_factor = minute_stats["error_rate"] / err_base
	return max(1.0, latency_factor, error_factor)


def _sample_status(multiplier: float, in_incident_window: bool, touches_affected: bool) -> str:
	if not in_incident_window or not touches_affected:
		p = random.random()
		if p < 0.004:
			return "error"
		if p < 0.006:
			return "timeout"
		return "ok"

	severity = max(0.0, multiplier - 1.0)
	timeout_prob = min(0.45, 0.015 + 0.09 * severity)
	error_prob = min(0.55, 0.03 + 0.12 * severity)
	p = random.random()
	if p < timeout_prob:
		return "timeout"
	if p < timeout_prob + error_prob:
		return "error"
	return "ok"


def generate_traces(
	incident: IncidentProfile,
	metrics: List[Dict],
	duration_minutes: int = 60,
	incident_start_minute: int = 30,
) -> List[Span]:
	if not metrics:
		return []

	start_time, minute_index = _build_metric_index(metrics)
	affected_services = set(incident.metric_effects.keys())

	spans: List[Span] = []

	for minute in range(duration_minutes):
		traces_this_minute = random.randint(5, 15)
		in_incident_window = minute >= incident_start_minute

		for _ in range(traces_this_minute):
			request_type = random.choice(list(REQUEST_FLOWS.keys()))
			flow = REQUEST_FLOWS[request_type]
			trace_id = uuid.uuid4().hex
			base_ts = start_time + timedelta(minutes=minute, seconds=random.uniform(0.0, 59.9))

			parent_span_id = None
			for idx, service in enumerate(flow):
				service_stats = minute_index.get(minute, {}).get(
					service,
					{
						"latency_p50": SERVICES[service]["latency_p50"],
						"latency_p99": SERVICES[service]["latency_p99"],
						"error_rate": SERVICES[service]["error_rate"],
					},
				)

				multiplier = _service_multiplier(service_stats, service)
				touches_affected = service in affected_services
				status = _sample_status(multiplier, in_incident_window, touches_affected)

				baseline_latency = float(SERVICES[service]["latency_p50"])
				jitter = random.uniform(0.92, 1.08)
				duration_ms = baseline_latency * multiplier * jitter

				if status == "timeout":
					duration_ms *= random.uniform(1.8, 2.8)
				elif status == "error":
					duration_ms *= random.uniform(1.1, 1.5)

				span_id = uuid.uuid4().hex[:16]
				span_start = base_ts + timedelta(milliseconds=idx * random.uniform(2.0, 9.0))

				spans.append(
					Span(
						trace_id=trace_id,
						span_id=span_id,
						parent_span_id=parent_span_id,
						service=service,
						operation=f"{request_type}.{service}",
						start_time=span_start.isoformat(),
						duration_ms=round(max(0.1, duration_ms), 3),
						status=status,
						error_message=_span_error_message(status, service),
					)
				)

				parent_span_id = span_id

	spans.sort(key=lambda span: (span.start_time, span.trace_id, span.span_id))
	return spans

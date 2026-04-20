"""Trace generation for simulator"""

import math
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

FLOW_WEIGHTS = {
    "user_auth": 0.48,
    "recommend": 0.34,
    "payment": 0.18,
}


def _flow_weights_for_incident(incident_name: str) -> Dict[str, float]:
    """Adjust request mix based on incident type to model realistic traffic shifts"""
    if incident_name == "bad_deployment":
        # Bad payment deployment causes users to avoid payment flow
        return {"user_auth": 0.62, "recommend": 0.34, "payment": 0.04}
    if incident_name in ("memory_leak", "cache_eviction_storm"):
        # Recommendation/cache issues shift load to auth/payment
        return {"user_auth": 0.55, "recommend": 0.18, "payment": 0.27}
    if incident_name == "database_lock":
        # Database issues affect all paths equally; traffic may drop overall but patterns consistent
        return {"user_auth": 0.48, "recommend": 0.34, "payment": 0.18}
    if incident_name == "cascading_timeout":
        # Database cascades to all; users abandon cart/transaction flows
        return {"user_auth": 0.70, "recommend": 0.20, "payment": 0.10}
    if incident_name == "network_spike":
        # Gateway issue; users retry simple auth, abandon recommendation/complex flows
        return {"user_auth": 0.58, "recommend": 0.24, "payment": 0.18}
    return FLOW_WEIGHTS


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
                "latency_p50": sum(float(r["latency_p50"]) for r in rows) / count,
                "latency_p99": sum(float(r["latency_p99"]) for r in rows) / count,
                "error_rate": sum(float(r["error_rate"]) for r in rows) / count,
            }

    return start_time, minute_index


def _service_multiplier(minute_stats: Dict[str, float], service: str) -> float:
    baseline = SERVICES[service]
    p99_base = max(0.001, float(baseline["latency_p99"]))
    err_base = max(0.000001, float(baseline["error_rate"]))

    latency_factor = minute_stats["latency_p99"] / p99_base
    error_factor = minute_stats["error_rate"] / err_base
    return max(1.0, latency_factor, error_factor)


def _sample_status(multiplier: float, in_incident_window: bool, touches_affected: bool) -> str:
    if not in_incident_window or not touches_affected:
        p = random.random()
        if p < 0.0007:
            return "error"
        if p < 0.0011:
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

def _sample_incident_status(
    incident_name: str,
    service: str,
    multiplier: float,
    in_incident_window: bool,
    touches_affected: bool,
) -> str:
    """Model incident-specific failure patterns"""
    if not in_incident_window or not touches_affected:
        p = random.random()
        if p < 0.0007:
            return "error"
        if p < 0.0011:
            return "timeout"
        return "ok"

    severity = max(0.0, multiplier - 1.0)

    # Memory leak: mostly timeouts (GC pauses), fewer errors
    if incident_name == "memory_leak":
        timeout_prob = min(0.55, 0.02 + 0.13 * severity)
        error_prob = min(0.25, 0.01 + 0.04 * severity)

    # Bad deployment: mostly errors (logic bugs), fewer soft timeouts
    elif incident_name == "bad_deployment":
        timeout_prob = min(0.15, 0.01 + 0.02 * severity)
        error_prob = min(0.70, 0.15 + 0.20 * severity)

    # Database lock: errors more than timeouts (lock held, instant fail)
    elif incident_name == "database_lock":
        timeout_prob = min(0.25, 0.01 + 0.05 * severity)
        error_prob = min(0.60, 0.08 + 0.15 * severity)

    # Cache eviction: mostly timeouts (slow miss lookup), gradual errors
    elif incident_name == "cache_eviction_storm":
        timeout_prob = min(0.50, 0.01 + 0.12 * severity)
        error_prob = min(0.30, 0.02 + 0.05 * severity)

    # Network spike: timeouts dominant (packet loss/latency)
    elif incident_name == "network_spike":
        timeout_prob = min(0.60, 0.05 + 0.15 * severity)
        error_prob = min(0.20, 0.01 + 0.03 * severity)

    # Cascading timeout: both high (cascade effect)
    elif incident_name == "cascading_timeout":
        timeout_prob = min(0.50, 0.02 + 0.12 * severity)
        error_prob = min(0.50, 0.05 + 0.15 * severity)

    else:
        timeout_prob = min(0.45, 0.015 + 0.09 * severity)
        error_prob = min(0.55, 0.03 + 0.12 * severity)

    p = random.random()
    if p < timeout_prob:
        return "timeout"
    if p < timeout_prob + error_prob:
        return "error"
    return "ok"

def _fallback_service_stats(service: str) -> Dict[str, float]:
    return {
        "latency_p50": float(SERVICES[service]["latency_p50"]),
        "latency_p99": float(SERVICES[service]["latency_p99"]),
        "error_rate": float(SERVICES[service]["error_rate"]),
    }


def _sample_request_type(weights: Dict[str, float]) -> str:
    request_types = list(weights.keys())
    weight_values = [weights[name] for name in request_types]
    return random.choices(request_types, weights=weight_values, k=1)[0]



def _sample_traces_this_minute(
    minute: int,
    duration_minutes: int,
    gateway_multiplier: float,
    in_incident_window: bool,
) -> int:
    phase = (minute / max(1, duration_minutes)) * 2.0 * math.pi
    diurnal = 9.0 + (3.0 * math.sin(phase))
    base_volume = diurnal + random.uniform(-1.5, 1.5)

    if in_incident_window and gateway_multiplier > 1.0:
        traffic_drop = min(0.55, (gateway_multiplier - 1.0) * 0.35)
        base_volume *= 1.0 - traffic_drop

    return max(3, min(16, int(round(base_volume))))


def _rollup_root_status(spans: List[Span]) -> None:
    if not spans:
        return

    child_statuses = [span.status for span in spans[1:]]
    root = spans[0]

    # Only some downstream failures bubble up to the edge to keep root error aligned with gateway metrics.
    if "timeout" in child_statuses and random.random() < 0.08:
        root.status = "timeout"
        root.error_message = _span_error_message("timeout", root.service)
        root.duration_ms = round(root.duration_ms * random.uniform(1.1, 1.35), 3)
    elif "error" in child_statuses and random.random() < 0.04:
        root.status = "error"
        root.error_message = _span_error_message("error", root.service)
        root.duration_ms = round(root.duration_ms * random.uniform(1.04, 1.18), 3)


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
    flow_weights = _flow_weights_for_incident(incident.name)

    spans: List[Span] = []

    for minute in range(duration_minutes):
        in_incident_window = minute >= incident_start_minute
        gateway_stats = minute_index.get(minute, {}).get("api-gateway", _fallback_service_stats("api-gateway"))
        gateway_multiplier = _service_multiplier(gateway_stats, "api-gateway")
        traces_this_minute = _sample_traces_this_minute(
            minute,
            duration_minutes,
            gateway_multiplier,
            in_incident_window,
        )

        for _ in range(traces_this_minute):
            request_type = _sample_request_type(flow_weights)
            flow = REQUEST_FLOWS[request_type]
            trace_id = uuid.uuid4().hex
            base_ts = start_time + timedelta(minutes=minute, seconds=random.uniform(0.0, 59.9))

            parent_span_id = None
            trace_spans: List[Span] = []
            current_offset_ms = random.uniform(0.0, 2.0)

            for idx, service in enumerate(flow):
                service_stats = minute_index.get(minute, {}).get(service, _fallback_service_stats(service))
                multiplier = _service_multiplier(service_stats, service)

                touches_affected = service in affected_services
                if idx == 0 and in_incident_window and gateway_multiplier > 1.2:
                    touches_affected = True

                status = _sample_incident_status(
                    incident.name,
                    service,
                    multiplier,
                    in_incident_window,
                    touches_affected,
                )

                baseline_latency = float(SERVICES[service]["latency_p50"])
                jitter = random.uniform(0.9, 1.12)
                duration_ms = baseline_latency * multiplier * jitter

                if status == "timeout":
                    duration_ms *= random.uniform(1.8, 2.8)
                elif status == "error":
                    duration_ms *= random.uniform(1.1, 1.5)

                span_id = uuid.uuid4().hex[:16]
                current_offset_ms += random.uniform(1.5, 7.5)
                span_start = base_ts + timedelta(milliseconds=current_offset_ms)

                trace_spans.append(
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

            _rollup_root_status(trace_spans)
            spans.extend(trace_spans)

    spans.sort(key=lambda span: (span.start_time, span.trace_id, span.span_id))
    return spans

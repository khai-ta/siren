"""Metric generation for simulator"""

import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from .incidents import IncidentProfile
from .topology import METRIC_KEYS, SERVICES

DEFAULT_GRADUAL_RAMP_MINUTES = 20.0
DEFAULT_RECOVERY_MINUTES = 2.0
BAD_DEPLOY_MIN_ONSET = 20
BAD_DEPLOY_MAX_ONSET = 40


def _noisy_value(base_value: float) -> float:
    pct_delta = max(-0.05, min(0.05, random.gauss(0.0, 0.015)))
    return base_value * (1.0 + pct_delta)


def _clamp_metric(metric: str, value: float) -> float:
    if metric in ("cpu", "memory"):
        return max(0.0, min(100.0, value))
    return max(0.0, value)


def _step_multiplier(target: float, minute_offset: float, onset_minute: float) -> float:
    return target if minute_offset >= onset_minute else 1.0


def _gradual_multiplier(
    target: float,
    minute_offset: float,
    onset_minute: float,
    ramp_minutes: float = DEFAULT_GRADUAL_RAMP_MINUTES,
) -> float:
    if minute_offset < onset_minute:
        return 1.0
    progress = min(1.0, (minute_offset - onset_minute) / max(ramp_minutes, 0.001))
    return 1.0 + (target - 1.0) * progress


def _spike_multiplier(
    target: float,
    minute_offset: float,
    onset_minute: float,
    rise_minutes: float,
    peak_minutes: float,
    fall_minutes: float,
) -> float:
    if minute_offset < onset_minute:
        return 1.0

    phase_minute = minute_offset - onset_minute

    if phase_minute < rise_minutes:
        progress = phase_minute / max(rise_minutes, 0.001)
        return 1.0 + (target - 1.0) * progress

    if phase_minute < rise_minutes + peak_minutes:
        return target

    if phase_minute < rise_minutes + peak_minutes + fall_minutes:
        fall_progress = (phase_minute - rise_minutes - peak_minutes) / max(fall_minutes, 0.001)
        return 1.0 + (target - 1.0) * (1.0 - fall_progress)

    return 1.0


def _incident_onset_minute(
    incident: IncidentProfile,
    incident_start_minute: int,
    bad_deploy_start_minute: int,
) -> float:
    if incident.name == "bad_deployment":
        return float(bad_deploy_start_minute)
    return float(incident_start_minute)


def _memory_leak_multiplier(
    effects: Dict[str, float],
    service: str,
    metric: str,
    minute_offset: float,
    onset_minute: float,
) -> float:
    if minute_offset < onset_minute:
        return 1.0

    minutes_since_onset = max(0.0, minute_offset - onset_minute)
    memory_growth = float(effects.get("memory_growth_per_minute", 1.0))
    latency_growth = float(effects.get("latency_p99_growth_per_minute", 1.0))
    threshold_memory = float(effects.get("error_rate_threshold_memory", 90.0))
    error_multiplier = float(effects.get("error_rate", 1.0))

    if metric == "memory":
        return memory_growth ** minutes_since_onset

    if metric == "latency_p99":
        return latency_growth ** minutes_since_onset

    if metric == "error_rate":
        baseline_memory = float(SERVICES[service]["memory"])
        memory_value = baseline_memory * (memory_growth ** minutes_since_onset)
        if memory_value > threshold_memory:
            # Ramp in error rate after threshold instead of a hard jump
            ramp_progress = min(1.0, max(0.0, (memory_value - threshold_memory) / 10.0))
            return 1.0 + (error_multiplier - 1.0) * ramp_progress
        return 1.0

    if metric == "cpu":
        # Leak pressure gradually increases CPU due to GC and allocator churn
        leak_pressure = max(0.0, (memory_growth ** minutes_since_onset) - 1.0)
        return 1.0 + leak_pressure * 0.35

    return 1.0


def _base_effect_multiplier(
    incident: IncidentProfile,
    service: str,
    metric: str,
    minute_offset: float,
    incident_start_minute: int,
    bad_deploy_start_minute: int,
) -> float:
    effects = incident.metric_effects.get(service, {})
    onset_minute = _incident_onset_minute(incident, incident_start_minute, bad_deploy_start_minute)

    if incident.name == "memory_leak" and service == "recommendation-service":
        return _memory_leak_multiplier(effects, service, metric, minute_offset, onset_minute)

    target_multiplier = float(effects.get(metric, 1.0))
    if target_multiplier == 1.0:
        return 1.0

    if incident.onset_style == "step":
        return _step_multiplier(target_multiplier, minute_offset, onset_minute)

    if incident.onset_style == "gradual":
        return _gradual_multiplier(target_multiplier, minute_offset, onset_minute)

    if incident.onset_style == "spike":
        rise = float(effects.get("spike_rise_minutes", 3.0))
        peak = float(effects.get("spike_peak_minutes", 10.0))
        fall = float(effects.get("spike_recovery_minutes", 5.0))
        return _spike_multiplier(target_multiplier, minute_offset, onset_minute, rise, peak, fall)

    return 1.0


def _apply_recovery(
    incident: IncidentProfile,
    current_multiplier: float,
    minute_offset: float,
    incident_start_minute: int,
    bad_deploy_start_minute: int,
    recovery_minutes: float = DEFAULT_RECOVERY_MINUTES,
) -> float:
    if not incident.recovers:
        return current_multiplier

    onset_minute = _incident_onset_minute(incident, incident_start_minute, bad_deploy_start_minute)
    recovery_start = onset_minute + float(incident.duration_minutes)

    if minute_offset <= recovery_start:
        return current_multiplier

    if minute_offset >= recovery_start + recovery_minutes:
        return 1.0

    progress = (minute_offset - recovery_start) / max(recovery_minutes, 0.001)
    return current_multiplier + (1.0 - current_multiplier) * progress


def generate_metrics(
    incident: IncidentProfile,
    duration_minutes: int = 60,
    tick_seconds: int = 10,
    incident_start_minute: int = 30,
) -> List[Dict]:
    rows: List[Dict] = []
    total_ticks = int((duration_minutes * 60) / tick_seconds)
    start_time = datetime.now(timezone.utc) - timedelta(minutes=duration_minutes)

    bad_deploy_start_minute = random.randint(BAD_DEPLOY_MIN_ONSET, BAD_DEPLOY_MAX_ONSET)

    for tick in range(total_ticks):
        ts = start_time + timedelta(seconds=tick * tick_seconds)
        minute_offset = (tick * tick_seconds) / 60.0

        for service, baseline in SERVICES.items():
            row: Dict[str, float] = {
                "timestamp": ts.isoformat(),
                "service": service,
            }

            for metric in METRIC_KEYS:
                base_value = _noisy_value(float(baseline[metric]))

                multiplier = _base_effect_multiplier(
                    incident=incident,
                    service=service,
                    metric=metric,
                    minute_offset=minute_offset,
                    incident_start_minute=incident_start_minute,
                    bad_deploy_start_minute=bad_deploy_start_minute,
                )

                multiplier = _apply_recovery(
                    incident=incident,
                    current_multiplier=multiplier,
                    minute_offset=minute_offset,
                    incident_start_minute=incident_start_minute,
                    bad_deploy_start_minute=bad_deploy_start_minute,
                )

                value = _clamp_metric(metric, base_value * multiplier)
                row[metric] = round(value, 6)

            rows.append(row)

    return rows

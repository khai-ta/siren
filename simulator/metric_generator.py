"""Metric generation for simulator"""

import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from .incidents import IncidentProfile
from .topology import DEPENDENCIES, METRIC_KEYS, SERVICES, hops_from_origin

DEFAULT_GRADUAL_RAMP_MINUTES = 20.0
DEFAULT_RECOVERY_MINUTES = 2.0
BAD_DEPLOY_MIN_ONSET = 20
BAD_DEPLOY_MAX_ONSET = 40
PROPAGATION_DELAY_MINUTES_PER_HOP = 0.75  # ~45 seconds per hop


def _noisy_value(base_value: float) -> float:
    pct_delta = max(-0.05, min(0.05, random.gauss(0.0, 0.015)))
    return base_value * (1.0 + pct_delta)


def _clamp_metric(metric: str, value: float) -> float:
    if metric in ("cpu", "memory"):
        return max(0.0, min(100.0, value))
    return max(0.0, value)


def _propagation_delay_minutes(service: str, origin: str) -> float:
    """Return the delay in minutes for the incident to propagate to this service"""
    hops = hops_from_origin(service, origin)
    if hops == 0:
        return 0.0
    return hops * PROPAGATION_DELAY_MINUTES_PER_HOP


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
    
    # Apply propagation delay based on graph distance before incident affects this service
    propagation_delay = _propagation_delay_minutes(service, incident.origin_service)
    adjusted_onset = onset_minute + propagation_delay

    if incident.name == "memory_leak" and service == "recommendation-service":
        return _memory_leak_multiplier(effects, service, metric, minute_offset, adjusted_onset)

    target_multiplier = float(effects.get(metric, 1.0))
    if target_multiplier == 1.0:
        return 1.0

    if incident.onset_style == "step":
        return _step_multiplier(target_multiplier, minute_offset, adjusted_onset)

    if incident.onset_style == "gradual":
        return _gradual_multiplier(target_multiplier, minute_offset, adjusted_onset)

    if incident.onset_style == "spike":
        rise = float(effects.get("spike_rise_minutes", 3.0))
        peak = float(effects.get("spike_peak_minutes", 10.0))
        fall = float(effects.get("spike_recovery_minutes", 5.0))
        return _spike_multiplier(target_multiplier, minute_offset, adjusted_onset, rise, peak, fall)

    return 1.0


def _apply_rps_degradation(
    error_multiplier: float,
    baseline_error: float,
) -> float:
    """Correlate RPS drop with error rate increase (clients back off)"""
    if error_multiplier <= 1.0:
        return 1.0
    
    # For every 2x error increase, RPS drops 15% (users abandon ship)
    error_increase = error_multiplier - 1.0
    rps_degradation = min(0.70, error_increase * 0.15)  # cap at 70% drop
    return max(0.3, 1.0 - rps_degradation)


def _apply_recovery_spike(
    incident: IncidentProfile,
    minute_offset: float,
    incident_start_minute: int,
    bad_deploy_start_minute: int,
    multiplier: float,
    metric: str,
) -> float:
    """Add thundering herd spike on recovery (secondary effect for error_rate and latency metrics).
    
    When an incident recovers, backed-up traffic and requests flood back, causing:
    - Brief spike in error rate (retries fail, timeouts)
    - Brief spike in latency (processing backlog)
    """
    if not incident.recovers or metric not in ("error_rate", "latency_p99", "latency_p50"):
        return multiplier
    
    onset_minute = _incident_onset_minute(incident, incident_start_minute, bad_deploy_start_minute)
    recovery_start = onset_minute + float(incident.duration_minutes)
    
    if minute_offset < recovery_start or minute_offset > recovery_start + 2.0:
        return multiplier
    
    # Subtle spike in first 2 minutes of recovery (backed-up load causes brief secondary spike)
    spike_phase = minute_offset - recovery_start
    spike_factor = 1.0 + (0.5 * (1.0 - spike_phase / 2.0))  # Decay from 1.5x to 1.0x
    return min(multiplier * spike_factor, multiplier * 1.5)


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

            # First pass: compute error_rate multiplier for RPS degradation correlation
            error_multiplier = _base_effect_multiplier(
                incident=incident,
                service=service,
                metric="error_rate",
                minute_offset=minute_offset,
                incident_start_minute=incident_start_minute,
                bad_deploy_start_minute=bad_deploy_start_minute,
            )
            error_multiplier = _apply_recovery(
                incident=incident,
                current_multiplier=error_multiplier,
                minute_offset=minute_offset,
                incident_start_minute=incident_start_minute,
                bad_deploy_start_minute=bad_deploy_start_minute,
            )
            # Apply recovery spike (secondary effect after recovery)
            error_multiplier = _apply_recovery_spike(
                incident=incident,
                minute_offset=minute_offset,
                incident_start_minute=incident_start_minute,
                bad_deploy_start_minute=bad_deploy_start_minute,
                multiplier=error_multiplier,
                metric="error_rate",
            )

            for metric in METRIC_KEYS:
                base_value = _noisy_value(float(baseline[metric]))

                # Use pre-computed error multiplier for error_rate
                if metric == "error_rate":
                    multiplier = error_multiplier
                else:
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
                    
                    # Apply recovery spike to latency_p99 and latency_p50
                    if metric in ("latency_p99", "latency_p50"):
                        multiplier = _apply_recovery_spike(
                            incident=incident,
                            minute_offset=minute_offset,
                            incident_start_minute=incident_start_minute,
                            bad_deploy_start_minute=bad_deploy_start_minute,
                            multiplier=multiplier,
                            metric=metric,
                        )

                # Apply RPS degradation if error rate is elevated
                if metric == "rps" and error_multiplier > 1.0:
                    # Apply RPS drop correlated with error rate increase
                    rps_multiplier = _apply_rps_degradation(error_multiplier, float(baseline["error_rate"]))
                    multiplier *= rps_multiplier

                value = _clamp_metric(metric, base_value * multiplier)
                row[metric] = round(value, 6)

            rows.append(row)

    return rows

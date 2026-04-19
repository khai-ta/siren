from dataclasses import dataclass
from typing import Dict

from .topology import DEPENDENCIES, INCIDENT_MULTIPLIERS, get_downstream_services


@dataclass(frozen=True)
class IncidentProfile:
    name: str
    display_name: str
    origin_service: str
    onset_style: str
    duration_minutes: int
    recovers: bool
    metric_effects: Dict[str, Dict[str, float]]
    description: str


def _clone_effects(effects: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
    return {service: dict(metrics) for service, metrics in effects.items()}


def _database_lock_effects() -> Dict[str, Dict[str, float]]:
    effects: Dict[str, Dict[str, float]] = {
        "database": {
            "latency_p99": 12.0,
            "error_rate": 15.0,
        }
    }

    for service in get_downstream_services("database"):
        effects[service] = {
            "latency_p99": 5.0,
            "error_rate": 8.0,
        }

    return effects


def _network_spike_effects() -> Dict[str, Dict[str, float]]:
    effects: Dict[str, Dict[str, float]] = {
        "api-gateway": {
            "latency_p99": 6.0,
            "latency_p50": 2.0,
            "spike_rise_minutes": 3.0,
            "spike_peak_minutes": 10.0,
            "spike_recovery_minutes": 5.0,
        }
    }

    for service in DEPENDENCIES["api-gateway"]:
        effects[service] = {
            "latency_p99": 2.0,
        }

    return effects


INCIDENT_PROFILES: Dict[str, IncidentProfile] = {
    "cascading_timeout": IncidentProfile(
        name="cascading_timeout",
        display_name="Cascading Timeout",
        origin_service="database",
        onset_style="step",
        duration_minutes=60,
        recovers=False,
        metric_effects=_clone_effects(INCIDENT_MULTIPLIERS),
        description="Database timeout causes immediate latency and error cascades through dependent services.",
    ),
    "memory_leak": IncidentProfile(
        name="memory_leak",
        display_name="Memory Leak",
        origin_service="recommendation-service",
        onset_style="gradual",
        duration_minutes=60,
        recovers=False,
        metric_effects={
            "recommendation-service": {
                "memory_growth_per_minute": 1.02,
                "latency_p99_growth_per_minute": 1.015,
                "error_rate_threshold_memory": 90.0,
                "error_rate": 5.0,
            }
        },
        description="Recommendation service memory usage rises over time until high memory triggers sharp error growth.",
    ),
    "database_lock": IncidentProfile(
        name="database_lock",
        display_name="Database Lock Contention",
        origin_service="database",
        onset_style="step",
        duration_minutes=15,
        recovers=True,
        metric_effects=_database_lock_effects(),
        description="A lock storm in the database sharply raises latency and errors, then releases after the lock window.",
    ),
    "bad_deployment": IncidentProfile(
        name="bad_deployment",
        display_name="Bad Deployment",
        origin_service="payment-service",
        onset_style="step",
        duration_minutes=60,
        recovers=False,
        metric_effects={
            "payment-service": {
                "error_rate": 25.0,
                "latency_p99": 1.5,
                "onset_minute_min": 20.0,
                "onset_minute_max": 40.0,
            }
        },
        description="A faulty payment release introduces logic errors with a random rollout onset and no automatic recovery.",
    ),
    "network_spike": IncidentProfile(
        name="network_spike",
        display_name="Network Spike",
        origin_service="api-gateway",
        onset_style="spike",
        duration_minutes=18,
        recovers=True,
        metric_effects=_network_spike_effects(),
        description="Gateway network instability rises quickly, holds, then recovers while adding latency to immediate dependencies.",
    ),
    "cache_eviction_storm": IncidentProfile(
        name="cache_eviction_storm",
        display_name="Cache Eviction Storm",
        origin_service="cache",
        onset_style="gradual",
        duration_minutes=20,
        recovers=True,
        metric_effects={
            "cache": {
                "error_rate": 8.0,
                "latency_p99": 4.0,
            },
            "recommendation-service": {
                "latency_p99": 3.0,
                "error_rate": 4.0,
            },
            "auth-service": {
                "latency_p99": 3.0,
                "error_rate": 4.0,
            },
        },
        description="Cache churn creates miss storms that gradually push dependency latency and errors higher until stabilization.",
    ),
}


INCIDENT_TYPES = list(INCIDENT_PROFILES.keys())


def get_incident_profile(name: str) -> IncidentProfile:
    try:
        return INCIDENT_PROFILES[name]
    except KeyError as exc:
        supported = ", ".join(INCIDENT_TYPES)
        raise ValueError(f"Unknown incident '{name}'. Supported incidents: {supported}") from exc

"""Siren simulator package"""

from .topology import (
    ANOMALY_KEYS,
    ANOMALY_SERVICE_ORDER,
    CRITICAL_EDGES,
    DEPENDENCIES,
    INCIDENT_MULTIPLIERS,
    LOG_TEMPLATES,
    METRIC_KEYS,
    SERVICES,
    get_downstream_services,
)

__all__ = [
    "SERVICES",
    "DEPENDENCIES",
    "INCIDENT_MULTIPLIERS",
    "LOG_TEMPLATES",
    "METRIC_KEYS",
    "ANOMALY_KEYS",
    "ANOMALY_SERVICE_ORDER",
    "CRITICAL_EDGES",
    "get_downstream_services",
]

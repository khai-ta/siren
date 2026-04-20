"""Siren simulator package"""

from .topology import (
    ANOMALY_KEYS,
    ANOMALY_SERVICE_ORDER,
    CRITICAL_EDGES,
    DEPENDENCIES,
    INCIDENT_MULTIPLIERS,
    LOG_TEMPLATES,
    METRIC_KEYS,
    SERVICE_POD_COUNTS,
    SERVICES,
    get_downstream_services,
    hops_from_origin,
)

__all__ = [
    "SERVICES",
    "DEPENDENCIES",
    "INCIDENT_MULTIPLIERS",
    "LOG_TEMPLATES",
    "METRIC_KEYS",
    "SERVICE_POD_COUNTS",
    "ANOMALY_KEYS",
    "ANOMALY_SERVICE_ORDER",
    "CRITICAL_EDGES",
    "get_downstream_services",
    "hops_from_origin",
]

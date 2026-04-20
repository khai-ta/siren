"""State schema for the autonomous investigation loop"""

from typing import Any, NotRequired, TypedDict


class HypothesisEntry(TypedDict):
    hypothesis: str
    evidence_for: list[str]
    evidence_against: list[str]
    confidence: float


class InvestigationState(TypedDict):
    incident_name: str
    query: str
    anomalies: list[dict[str, Any]]
    origin_service: str
    window_start: str
    window_end: str
    top_k: int
    step_count: int
    max_steps: int
    confidence: float
    done: bool
    current_focus: str
    retrieved: dict[str, Any]
    hypothesis_ledger: list[HypothesisEntry]
    reasoning_trace: list[str]
    final_report: NotRequired[str]
    report_path: NotRequired[str]
    uncached_latency_ms: NotRequired[float]
    cached_latency_ms: NotRequired[float]
    error: NotRequired[str]

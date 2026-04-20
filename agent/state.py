"""State schema for the autonomous investigation graph"""

from operator import add
from typing import Any, Annotated, TypedDict


class Hypothesis(TypedDict):
    id: str
    statement: str
    confidence: float
    evidence_for: list[str]
    evidence_against: list[str]
    status: str


class ToolCall(TypedDict):
    step: int
    tool_name: str
    arguments: dict[str, Any]
    result_summary: str
    timestamp: str


class InvestigationState(TypedDict):
    # Input
    incident_id: str
    anomalies: list[dict[str, Any]]
    origin_service: str
    window_start: str
    window_end: str

    # Agent working memory
    investigation_plan: list[str]
    current_step: int
    hypotheses: Annotated[list[Hypothesis], add]
    tool_history: Annotated[list[ToolCall], add]
    evidence_ledger: Annotated[dict[str, dict[str, Any]], lambda a, b: {**a, **b}]

    # Control
    max_steps: int
    should_conclude: bool

    # Output
    final_root_cause: str | None
    final_confidence: float | None
    final_report: str | None

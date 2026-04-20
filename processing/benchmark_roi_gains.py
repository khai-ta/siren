"""Benchmark token savings from high-ROI prompt optimizations"""

from agent.state import InvestigationState
from processing.prompt_builder import build_investigator_prompt


def estimate_prompt_size(text: str) -> int:
    """Estimate tokens (rough: 4 chars per token)"""
    return len(text) // 4


def simulate_investigation_state(step: int) -> InvestigationState:
    """Create a realistic investigation state at a given step"""
    return {
        "incident_id": "test-123",
        "anomalies": [
            {"service": "database", "metric": "latency_p99", "zscore": 8.5, "value": 245},
            {"service": "auth-service", "metric": "error_rate", "zscore": 5.2, "value": 0.08},
            {"service": "api-gateway", "metric": "latency_p99", "zscore": 4.1, "value": 180},
        ],
        "origin_service": "database",
        "window_start": "2026-04-20T03:00:00",
        "window_end": "2026-04-20T04:00:00",
        "investigation_plan": [
            "Verify database latency spike by checking metrics",
            "Inspect database query logs for timeouts",
            "Check database lock contention and deadlocks",
            "Review recent database schema changes or deployments",
        ],
        "current_step": step,
        "hypotheses": [
            {
                "id": "h1",
                "statement": "database query timeout causing downstream latency",
                "confidence": 0.7,
                "evidence_for": ["ev_1", "ev_2"],
                "evidence_against": [],
                "status": "open",
            },
            {
                "id": "h2",
                "statement": "database lock contention from concurrent writes",
                "confidence": 0.5,
                "evidence_for": ["ev_2"],
                "evidence_against": [],
                "status": "open",
            },
            {
                "id": "h3",
                "statement": "recent deployment introduced slow query",
                "confidence": 0.3,
                "evidence_for": [],
                "evidence_against": ["ev_1"],
                "status": "rejected",
            },
            {
                "id": "h4",
                "statement": "memory exhaustion on database instance",
                "confidence": 0.2,
                "evidence_for": [],
                "evidence_against": ["ev_3"],
                "status": "rejected",
            },
        ],
        "tool_history": [
            {
                "step": 1,
                "tool_name": "get_metrics",
                "arguments": {
                    "service": "database",
                    "window_start": "2026-04-20T03:00:00",
                    "window_end": "2026-04-20T04:00:00",
                },
                "result_summary": "latency_p99 30ms->245ms (8.1x), error_rate 0.1%->1.2% (12x)",
                "timestamp": "2026-04-20T03:05:00",
            },
            {
                "step": 2,
                "tool_name": "query_logs",
                "arguments": {
                    "service": "database",
                    "query": "timeout",
                    "window_start": "2026-04-20T03:00:00",
                    "window_end": "2026-04-20T04:00:00",
                },
                "result_summary": "list[5]",
                "timestamp": "2026-04-20T03:10:00",
            },
            {
                "step": 3,
                "tool_name": "get_dependencies",
                "arguments": {"service": "database"},
                "result_summary": "list[0]",
                "timestamp": "2026-04-20T03:15:00",
            },
        ],
        "evidence_ledger": {
            "ev_1": {
                "step": 1,
                "tool": "get_metrics",
                "data": {"latency_p99_peak": 245, "error_rate_peak": 0.012},
            },
            "ev_2": {
                "step": 2,
                "tool": "query_logs",
                "data": "Query execution timeout after 2500ms - table: orders",
            },
            "ev_3": {
                "step": 3,
                "tool": "get_dependencies",
                "data": {"dependencies": []},
            },
        },
        "max_steps": 15,
        "should_conclude": False,
        "final_root_cause": None,
        "final_confidence": None,
        "final_report": None,
    }


if __name__ == "__main__":
    print("\nPrompt size comparison (tokens per step):")
    print("-" * 70)

    for step in [1, 5, 10, 15]:
        state = simulate_investigation_state(step)
        prompt = build_investigator_prompt(state)
        tokens = estimate_prompt_size(prompt)
        print(f"Step {step:2}: {tokens:>5} tokens")

    print("\nFull state summary at step 10:")
    state = simulate_investigation_state(10)
    prompt = build_investigator_prompt(state)
    print(f"Total prompt size: {estimate_prompt_size(prompt)} tokens")
    print(f"\nActual prompt:\n{prompt[:500]}...")

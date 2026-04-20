"""LangGraph nodes for autonomous incident investigation"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langsmith import traceable

from agent.prompts import (
    INVESTIGATOR_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    REPORTER_SYSTEM_PROMPT,
    VERIFIER_SYSTEM_PROMPT,
)
from agent.state import Hypothesis, InvestigationState, ToolCall
from agent.tools import INVESTIGATION_TOOLS
from processing.prompt_builder import build_investigator_prompt
from processing.log_compressor import cluster_similar_logs
from processing.metric_summarizer import summarize_metrics
from processing.trace_condenser import condense_trace_errors
from processing.evidence_digest import build_evidence_digest


_fast_llm = ChatAnthropic(model="claude-haiku-4-5", temperature=0)
_reasoning_llm = ChatAnthropic(
    model="claude-sonnet-4-6",
    temperature=0,
    extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
)
_reasoning_llm_with_tools = _reasoning_llm.bind_tools(INVESTIGATION_TOOLS)


@traceable(name="plan_investigation")
def plan_investigation(state: InvestigationState) -> dict[str, Any]:
    """Planner node that produces the investigation plan from anomalies"""
    anomalies_summary = "\n".join(
        f"- {a['service']}: {a['metric']} z-score={float(a.get('zscore', 0.0)):.1f}"
        for a in state["anomalies"]
    )

    response = _reasoning_llm.invoke(
        [
            SystemMessage(
                content=PLANNER_SYSTEM_PROMPT,
                additional_kwargs={"cache_control": {"type": "ephemeral"}},
            ),
            HumanMessage(
                content=(
                    "Anomalies detected:\n"
                    f"{anomalies_summary}\n\n"
                    f"Origin service candidate: {state['origin_service']}\n\n"
                    "Produce your investigation plan as a JSON list of steps"
                )
            ),
        ]
    )

    parsed = _extract_json_object(str(response.content))
    plan: list[str] = parsed.get("plan") or _extract_json_list(str(response.content))
    competing_statement: str = str(parsed.get("competing_hypothesis") or "")

    if not plan:
        plan = [
            "Validate the earliest anomaly timing and service ownership",
            "Inspect dependencies of the suspected origin service",
            "Gather logs, traces, and metrics to confirm or reject hypotheses",
        ]

    primary_hypothesis: Hypothesis = {
        "id": str(uuid.uuid4())[:8],
        "statement": f"{state['origin_service']} is the root cause of the incident",
        "confidence": 0.3,
        "evidence_for": [],
        "evidence_against": [],
        "status": "open",
    }

    hypotheses: list[Hypothesis] = [primary_hypothesis]

    if competing_statement:
        rival_hypothesis: Hypothesis = {
            "id": str(uuid.uuid4())[:8],
            "statement": competing_statement,
            "confidence": 0.2,
            "evidence_for": [],
            "evidence_against": [],
            "status": "open",
        }
        hypotheses.append(rival_hypothesis)

    return {
        "investigation_plan": plan,
        "hypotheses": hypotheses,
        "current_step": 0,
    }


@traceable(name="investigate_step")
def investigate_step(state: InvestigationState) -> dict[str, Any]:
    """Investigator node that picks one tool call based on current state"""
    step = state["current_step"] + 1
    remaining = state["max_steps"] - step

    compressed_state = build_investigator_prompt(state)

    response = _reasoning_llm_with_tools.invoke(
        [
            SystemMessage(
                content=INVESTIGATOR_SYSTEM_PROMPT,
                additional_kwargs={"cache_control": {"type": "ephemeral"}},
            ),
            HumanMessage(
                content=f"{compressed_state}\n\nWhat tool should you call next? Return one tool call or set should_conclude."
            ),
        ]
    )

    content_lower = str(response.content).lower()
    if "should_conclude" in content_lower or remaining <= 0:
        return {
            "current_step": step,
            "should_conclude": True,
        }

    if not response.tool_calls:
        return {
            "current_step": step,
            "should_conclude": True,
        }

    tool_call = response.tool_calls[0]
    tool_result = _execute_tool(tool_call)

    tool_record: ToolCall = {
        "step": step,
        "tool_name": str(tool_call["name"]),
        "arguments": dict(tool_call["args"]),
        "result_summary": _summarize_result(tool_result),
        "timestamp": datetime.utcnow().isoformat(),
    }

    evidence_id = f"ev_{step}"
    evidence_entry = {
        evidence_id: {
            "step": step,
            "tool": tool_call["name"],
            "data": tool_result,
        }
    }

    hypothesis_updates = _classify_evidence_relevance(
        state["hypotheses"],
        tool_call,
        tool_result,
        evidence_id,
    )

    return {
        "current_step": step,
        "tool_history": [tool_record],
        "evidence_ledger": evidence_entry,
        "hypotheses": hypothesis_updates,
    }


@traceable(name="verify_hypothesis")
def verify_hypothesis(state: InvestigationState) -> dict[str, Any]:
    """Verifier node that determines final root cause and confidence"""
    state_summary = _build_state_summary(state)

    response = _reasoning_llm.invoke(
        [
            SystemMessage(
                content=VERIFIER_SYSTEM_PROMPT,
                additional_kwargs={"cache_control": {"type": "ephemeral"}},
            ),
            HumanMessage(content=f"Investigation state:\n{state_summary}\n\nVerify the root cause"),
        ]
    )

    verdict = _extract_json_object(str(response.content))

    root_cause = str(verdict.get("root_cause") or state["origin_service"])
    confidence = float(verdict.get("confidence") or 0.5)

    return {
        "final_root_cause": root_cause,
        "final_confidence": confidence,
    }


@traceable(name="write_report")
def write_report(state: InvestigationState) -> dict[str, Any]:
    """Reporter node that produces the final markdown RCA"""
    state_summary = _build_state_summary(state)

    response = _reasoning_llm.invoke(
        [
            SystemMessage(
                content=REPORTER_SYSTEM_PROMPT,
                additional_kwargs={"cache_control": {"type": "ephemeral"}},
            ),
            HumanMessage(content=f"Investigation complete\n\n{state_summary}\n\nWrite the final RCA report"),
        ]
    )

    return {
        "final_report": str(response.content),
    }


def should_continue(state: InvestigationState) -> str:
    if state["should_conclude"]:
        return "verify"
    if state["current_step"] >= state["max_steps"]:
        return "verify"
    return "investigate"


def _extract_json_list(text: str) -> list[str]:
    """Parse a JSON list from potentially messy LLM output"""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []

    snippet = text[start : end + 1]
    try:
        parsed = json.loads(snippet)
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _extract_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from LLM output"""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}

    snippet = text[start : end + 1]
    try:
        parsed = json.loads(snippet)
    except json.JSONDecodeError:
        return {}

    if not isinstance(parsed, dict):
        return {}
    return parsed


def _execute_tool(tool_call: dict[str, Any]) -> Any:
    """Execute a tool call and compress results based on tool type"""
    tool_map = {t.name: t for t in INVESTIGATION_TOOLS}
    tool = tool_map[str(tool_call["name"])]
    raw_result = tool.invoke(tool_call["args"])

    # Apply tool-specific compression
    tool_name = str(tool_call["name"])

    if tool_name == "query_logs":
        # raw_result is list of log dicts
        compressed = cluster_similar_logs(raw_result, max_per_cluster=3)
        return "\n".join(compressed)

    if tool_name == "get_metrics":
        # raw_result is {"baseline": {...}, "peak": {...}}
        service = tool_call["args"].get("service", "unknown")
        return summarize_metrics(
            service,
            raw_result.get("baseline", {}),
            raw_result.get("peak", {}),
        )

    if tool_name == "get_trace_errors":
        return condense_trace_errors(raw_result)

    # Other tools (get_dependencies, get_callers, get_blast_radius, search_runbook)
    # return short lists or small results — no compression needed
    return raw_result


def _summarize_result(result: Any) -> str:
    """Compress a tool result into one line for the history log"""
    if isinstance(result, list):
        return f"returned list[{len(result)}]"
    if isinstance(result, dict):
        keys = ", ".join(list(result.keys())[:5])
        return f"returned object keys: {keys or '(none)'}"
    text = str(result).strip().replace("\n", " ")
    return text[:220] if text else "empty result"


def _classify_evidence_relevance(
    hypotheses: list[Hypothesis],
    tool_call: dict[str, Any],
    tool_result: Any,
    evidence_id: str,
) -> list[Hypothesis]:
    """Use fast LLM to classify whether new evidence supports or rejects each hypothesis"""
    if not hypotheses:
        return []

    prompt = {
        "tool_name": tool_call.get("name"),
        "tool_args": tool_call.get("args", {}),
        "result_summary": _summarize_result(tool_result),
        "hypotheses": hypotheses,
        "instruction": (
            "Return JSON list where each item has id, supports (bool), rejects (bool), confidence_delta (-0.3 to 0.3)"
        ),
    }

    updates: list[dict[str, Any]] = []
    try:
        response = _fast_llm.invoke(
            [
                SystemMessage(content="Classify evidence relevance for hypotheses"),
                HumanMessage(content=json.dumps(prompt, ensure_ascii=True)),
            ]
        )
        parsed = _extract_json_list(str(response.content))
        if parsed:
            maybe_json = _extract_json_object(str(response.content))
            if isinstance(maybe_json.get("updates"), list):
                updates = [u for u in maybe_json["updates"] if isinstance(u, dict)]
            else:
                raw = str(response.content)
                first = raw.find("[")
                last = raw.rfind("]")
                if first != -1 and last != -1 and last > first:
                    try:
                        loaded = json.loads(raw[first : last + 1])
                        if isinstance(loaded, list):
                            updates = [u for u in loaded if isinstance(u, dict)]
                    except json.JSONDecodeError:
                        updates = []
    except Exception:
        updates = []

    update_map = {str(u.get("id")): u for u in updates}
    revised: list[Hypothesis] = []
    for hypothesis in hypotheses:
        current = dict(hypothesis)
        item = update_map.get(hypothesis["id"], {})

        supports = bool(item.get("supports", False))
        rejects = bool(item.get("rejects", False))
        delta = float(item.get("confidence_delta", 0.0))
        delta = max(-0.3, min(0.3, delta))

        if not item:
            # No classification from fast LLM — record evidence neutrally without
            # boosting confidence; keyword-matching alone is unreliable because most
            # tool results during incidents contain error keywords regardless of origin
            supports = False
            rejects = False
            delta = 0.0

        if supports:
            current["evidence_for"] = [*current["evidence_for"], evidence_id]
        if rejects:
            current["evidence_against"] = [*current["evidence_against"], evidence_id]

        current["confidence"] = max(0.0, min(1.0, current["confidence"] + delta))

        if current["confidence"] >= 0.8 and len(current["evidence_for"]) >= 2:
            current["status"] = "confirmed"
        elif len(current["evidence_against"]) >= 2 and current["confidence"] <= 0.35:
            current["status"] = "rejected"
        else:
            current["status"] = "open"

        revised.append(current)  # type: ignore[arg-type]

    return revised


def _build_state_summary(state: InvestigationState) -> str:
    """Format investigation state for verifier and reporter prompts"""
    anomalies_summary = "\n".join(
        f"- {a['service']} {a['metric']}={a.get('value', 'n/a')} z={a.get('zscore', 'n/a')}"
        for a in state["anomalies"][:8]
    )
    hypotheses_summary = "\n".join(
        (
            f"- {h['id']} | {h['statement']} | status={h['status']} | "
            f"confidence={h['confidence']:.2f} | "
            f"for={len(h['evidence_for'])}, against={len(h['evidence_against'])}"
        )
        for h in state["hypotheses"]
    )
    history_summary = "\n".join(
        f"- Step {tc['step']} {tc['tool_name']} -> {tc['result_summary']}"
        for tc in state["tool_history"]
    )

    sections = [
        f"incident_id: {state['incident_id']}",
        f"origin_service: {state['origin_service']}",
        f"window: {state['window_start']} to {state['window_end']}",
        f"current_step: {state['current_step']} / {state['max_steps']}",
        f"should_conclude: {state['should_conclude']}",
        f"\nAnomalies:\n{anomalies_summary or '(none)'}",
    ]

    # Include plan only in early steps (static after planner)
    if state["current_step"] <= 3:
        sections.append("Plan:\n" + "\n".join(f"- {step}" for step in state["investigation_plan"]))

    sections.extend([
        f"Hypotheses:\n{hypotheses_summary or '(none)'}",
        f"Tool history:\n{history_summary or '(none)'}",
        f"Evidence:\n{build_evidence_digest(state['evidence_ledger'])}",
    ])

    return "\n\n".join(sections)

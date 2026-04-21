"""FastAPI service API for retrieval, investigation, and evaluation"""

import os
import statistics
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent.run import run_investigation
from evaluation.run_benchmark import run_benchmark
from retrieval.orchestrator import SirenQueryEngine
from feedback.store import FeedbackStore

app = FastAPI(title="SIREN Retrieval API", version="1.0.0")
_engine: SirenQueryEngine | None = None
_store = FeedbackStore()


def _get_engine() -> SirenQueryEngine:
	global _engine
	if _engine is None:
		_engine = SirenQueryEngine()
	return _engine


class RetrieveRequest(BaseModel):
	query: str
	anomalies: list[dict[str, Any]]
	origin_service: str
	window_start: str
	window_end: str


class EvaluateRequest(BaseModel):
	seed: int = Field(default=7, ge=0)


class FeedbackRequest(BaseModel):
	incident_id: str
	verdict: str
	correct_root_cause: str | None = None
	engineer_notes: str | None = None


def _summarize_scores(results: list[dict[str, Any]]) -> dict[str, float]:
	buckets: dict[str, list[float]] = {}
	for result in results:
		score = result.get("score", {})
		for key, value in score.items():
			if isinstance(value, (int, float)):
				buckets.setdefault(key, []).append(float(value))

	averages = {key: statistics.mean(values) for key, values in buckets.items() if values}
	if averages:
		averages["overall_average"] = statistics.mean(averages.values())
	else:
		averages["overall_average"] = 0.0
	return averages


@app.get("/health")
def health() -> dict[str, Any]:
	return {
		"status": "ok",
		"api": "ready",
		"env": {
			"openai": bool(os.getenv("OPENAI_API_KEY")),
			"pinecone": bool(os.getenv("PINECONE_API_KEY")),
			"cohere": bool(os.getenv("COHERE_API_KEY")),
			"anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
		},
	}


@app.post("/retrieve")
def retrieve(payload: RetrieveRequest) -> dict[str, Any]:
	try:
		engine = _get_engine()
		return engine.retrieve(
			query=payload.query,
			anomalies=payload.anomalies,
			origin_service=payload.origin_service,
			window_start=payload.window_start,
			window_end=payload.window_end,
		)
	except Exception as exc:
		raise HTTPException(status_code=503, detail=f"retrieval backend unavailable: {exc}") from exc


@app.post("/investigate")
def investigate(payload: RetrieveRequest) -> dict[str, Any]:
	try:
		final_state = run_investigation(
			anomalies=payload.anomalies,
			origin_service=payload.origin_service,
			window_start=payload.window_start,
			window_end=payload.window_end,
		)
	except Exception as exc:
		raise HTTPException(status_code=500, detail=f"investigation failed: {exc}") from exc

	return {
		"root_cause": final_state["final_root_cause"],
		"confidence": final_state["final_confidence"],
		"report": final_state["final_report"],
		"steps_taken": final_state["current_step"],
		"tool_history": final_state["tool_history"],
	}


@app.post("/evaluate")
def evaluate(payload: EvaluateRequest) -> dict[str, Any]:
	try:
		results = run_benchmark(seed=payload.seed)
	except Exception as exc:
		raise HTTPException(status_code=500, detail=f"evaluation failed: {exc}") from exc

	return {
		"seed": payload.seed,
		"results": results,
		"averages": _summarize_scores(results),
	}


@app.post("/feedback")
def submit_feedback(req: FeedbackRequest) -> dict[str, Any]:
	_store.save_feedback(
		incident_id=req.incident_id,
		verdict=req.verdict,
		correct_root_cause=req.correct_root_cause,
		engineer_notes=req.engineer_notes,
	)
	return {"status": "ok"}


@app.get("/investigations")
def list_investigations(limit: int = 50) -> list[dict[str, Any]]:
	return _store.list_investigations(limit=limit)

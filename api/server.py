"""FastAPI service API for retrieval, investigation, and evaluation"""

import os
import statistics
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from evaluation.run_benchmark import run_benchmark
from investigate import run_investigation
from retrieval.orchestrator import SirenQueryEngine

app = FastAPI(title="SIREN Retrieval API", version="1.0.0")
_engine: SirenQueryEngine | None = None


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


class InvestigateRequest(BaseModel):
	metrics_csv: str = Field(..., description="Path to metrics CSV")
	top_k: int = Field(default=12, ge=1, le=50)
	reindex: bool = Field(default=True)
	use_agent: bool = Field(default=False)


class EvaluateRequest(BaseModel):
	seed: int = Field(default=7, ge=0)


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
def investigate(payload: InvestigateRequest) -> dict[str, Any]:
	metrics_path = Path(payload.metrics_csv)
	if not metrics_path.exists():
		raise HTTPException(status_code=404, detail=f"metrics file not found: {payload.metrics_csv}")

	try:
		result = run_investigation(
			metrics_path,
			top_k=payload.top_k,
			reindex=payload.reindex,
			use_agent=payload.use_agent,
		)
	except Exception as exc:
		raise HTTPException(status_code=500, detail=f"investigation failed: {exc}") from exc

	return {
		"incident_name": result["incident_name"],
		"origin_service": result["origin_service"],
		"anomaly_metric": result["anomaly_metric"],
		"query": result["query"],
		"report": result["report"],
		"report_path": str(result["report_path"]),
		"uncached_latency_ms": result["uncached_latency_ms"],
		"cached_latency_ms": result["cached_latency_ms"],
		"retrieved": result["retrieved"],
		"reasoning_trace": result.get("reasoning_trace", []),
		"hypothesis_ledger": result.get("hypothesis_ledger", []),
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

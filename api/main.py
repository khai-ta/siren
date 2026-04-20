"""FastAPI scaffold for retrieval service"""

from typing import Any, Dict, List

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="SIREN Retrieval API", version="0.1.0")


class InvestigateRequest(BaseModel):
    incident: str = Field(..., description="Incident identifier")
    question: str = Field(default="What is the most likely root cause and blast radius?")
    top_k: int = Field(default=12, ge=1, le=50)


class EvaluateRequest(BaseModel):
    dataset_name: str = Field(..., description="Evaluation dataset name")
    sample_size: int = Field(default=20, ge=1, le=500)


def _placeholder_evidence() -> List[Dict[str, Any]]:
    return [
        {
            "evidence_id": "placeholder-1",
            "source": "runbook",
            "text": "Retrieval pipeline scaffold is in setup mode",
            "score": 0.0,
        }
    ]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mode": "scaffold"}


@app.post("/investigate")
def investigate(payload: InvestigateRequest) -> Dict[str, Any]:
    return {
        "mode": "scaffold",
        "incident": payload.incident,
        "question": payload.question,
        "top_k": payload.top_k,
        "answer": "Investigation flow is not implemented yet",
        "evidence": _placeholder_evidence(),
    }


@app.post("/evaluate")
def evaluate(payload: EvaluateRequest) -> Dict[str, Any]:
    return {
        "mode": "scaffold",
        "dataset_name": payload.dataset_name,
        "sample_size": payload.sample_size,
        "metrics": {},
        "summary": "Evaluation flow is not implemented yet",
    }

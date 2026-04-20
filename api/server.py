"""FastAPI service layer for retrieval"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from retrieval.orchestrator import SirenQueryEngine

app = FastAPI(title="Siren Retrieval Service")
_engine: SirenQueryEngine | None = None


def _get_engine() -> SirenQueryEngine:
    global _engine
    if _engine is None:
        _engine = SirenQueryEngine()
    return _engine


class RetrieveRequest(BaseModel):
    query: str
    anomalies: list[dict]
    origin_service: str
    window_start: str
    window_end: str


@app.post("/retrieve")
def retrieve(req: RetrieveRequest):
    try:
        engine = _get_engine()
        return engine.retrieve(
            query=req.query,
            anomalies=req.anomalies,
            origin_service=req.origin_service,
            window_start=req.window_start,
            window_end=req.window_end,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"retrieval backend unavailable: {exc}") from exc


@app.get("/health")
def health():
    return {"status": "ok"}

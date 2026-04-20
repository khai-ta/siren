"""FastAPI service layer for retrieval"""

from fastapi import FastAPI
from pydantic import BaseModel

from retrieval.orchestrator import SirenQueryEngine

app = FastAPI(title="Siren Retrieval Service")
engine = SirenQueryEngine()


class RetrieveRequest(BaseModel):
    query: str
    anomalies: list[dict]
    origin_service: str
    window_start: str
    window_end: str


@app.post("/retrieve")
def retrieve(req: RetrieveRequest):
    return engine.retrieve(
        query=req.query,
        anomalies=req.anomalies,
        origin_service=req.origin_service,
        window_start=req.window_start,
        window_end=req.window_end,
    )


@app.get("/health")
def health():
    return {"status": "ok"}

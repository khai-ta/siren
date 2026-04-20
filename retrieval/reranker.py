"""Reranker scaffold using Cohere"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class RerankedEvidence:
    evidence_id: str
    text: str
    metadata: Dict
    source: str
    score: float


class CohereReranker:
    """Placeholder reranker interface"""

    def __init__(self, api_key: str, model: str = "rerank-english-v3.0") -> None:
        self.api_key = api_key
        self.model = model

    def rerank(self, query: str, items: List[RerankedEvidence], top_k: int = 12) -> List[RerankedEvidence]:
        return []

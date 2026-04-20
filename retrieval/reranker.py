"""Cohere reranker wrapper"""

import os
from dataclasses import dataclass
from typing import Dict, List

import cohere


@dataclass
class RerankedEvidence:
    evidence_id: str
    text: str
    metadata: Dict
    source: str
    score: float


class CohereReranker:
    """Second-stage reranker using Cohere Rerank v3"""

    def __init__(self) -> None:
        self.client = cohere.Client(api_key=os.getenv("COHERE_API_KEY"))
        self.model = "rerank-english-v3.0"

    def rerank(self, query: str, documents: List[Dict], top_n: int = 10) -> List[Dict]:
        """Take candidate docs and return top results by true relevance"""
        if not documents:
            return []

        texts = [str(doc.get("text", "")) for doc in documents]
        response = self.client.rerank(
            model=self.model,
            query=query,
            documents=texts,
            top_n=top_n,
        )

        reranked: List[Dict] = []
        for result in response.results:
            original = documents[result.index]
            reranked.append(
                {
                    **original,
                    "rerank_score": result.relevance_score,
                }
            )
        return reranked

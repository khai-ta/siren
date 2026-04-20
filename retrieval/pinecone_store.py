"""Pinecone serverless wrapper with OpenAI embeddings"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec


@dataclass
class VectorEvidence:
    evidence_id: str
    text: str
    metadata: Dict
    score: float


class PineconeStore:
    """Pinecone index wrapper with embedding + search helpers"""

    def __init__(self, index_name: str, dimension: int = 1536) -> None:
        self.pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self.openai = OpenAI()
        self.index_name = index_name
        self.dimension = dimension

        self._ensure_index(index_name)
        self.index = self.pc.Index(index_name)

    def _list_index_names(self) -> List[str]:
        raw = self.pc.list_indexes()

        if hasattr(raw, "names"):
            return list(raw.names())

        names: List[str] = []
        for idx in raw:
            if isinstance(idx, str):
                names.append(idx)
            else:
                name = getattr(idx, "name", None)
                if name:
                    names.append(name)
        return names

    def _ensure_index(self, index_name: str) -> None:
        if index_name in self._list_index_names():
            return

        self.pc.create_index(
            name=index_name,
            dimension=self.dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )

    def embed(self, texts: List[str]) -> List[List[float]]:
        response = self.openai.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
        )
        return [r.embedding for r in response.data]

    def upsert(self, docs: List[str], metadatas: List[Dict], ids: List[str]) -> None:
        if not (len(docs) == len(metadatas) == len(ids)):
            raise ValueError("docs, metadatas, and ids must have the same length")

        chunk_size = 100
        for i in range(0, len(docs), chunk_size):
            doc_chunk = docs[i : i + chunk_size]
            metadata_chunk = metadatas[i : i + chunk_size]
            id_chunk = ids[i : i + chunk_size]

            vectors = self.embed(doc_chunk)
            records = []
            for item_id, vector, text, metadata in zip(id_chunk, vectors, doc_chunk, metadata_chunk):
                merged_metadata = {**metadata, "text": text}
                records.append(
                    {
                        "id": item_id,
                        "values": vector,
                        "metadata": merged_metadata,
                    }
                )

            self.index.upsert(vectors=records)

    def search(self, query: str, top_k: int = 50, filter: Optional[Dict] = None) -> List[Dict]:
        query_vec = self.embed([query])[0]
        results = self.index.query(
            vector=query_vec,
            top_k=top_k,
            include_metadata=True,
            filter=filter,
        )
        return [
            {
                "id": m.id,
                "text": (m.metadata or {}).get("text"),
                "metadata": m.metadata or {},
                "score": m.score,
            }
            for m in results.matches
        ]

    def query(self, query_vector: List[float], top_k: int = 8, namespace: Optional[str] = None) -> List[VectorEvidence]:
        kwargs: Dict = {
            "vector": query_vector,
            "top_k": top_k,
            "include_metadata": True,
        }
        if namespace is not None:
            kwargs["namespace"] = namespace

        results = self.index.query(**kwargs)
        return [
            VectorEvidence(
                evidence_id=m.id,
                text=(m.metadata or {}).get("text", ""),
                metadata=m.metadata or {},
                score=m.score,
            )
            for m in results.matches
        ]

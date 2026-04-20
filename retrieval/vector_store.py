"""ChromaDB vector store scaffold"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class RetrievedItem:
    item_id: str
    text: str
    metadata: Dict
    score: float
    source: str


class VectorStore:
    """Placeholder wrapper for future log/doc semantic retrieval"""

    def __init__(self, persist_dir: str) -> None:
        self.persist_dir = persist_dir

    def upsert(
        self,
        collection: str,
        ids: List[str],
        documents: List[str],
        metadatas: List[Dict],
    ) -> None:
        return None

    def query(
        self,
        collection: str,
        query_text: str,
        n_results: int = 8,
        where: Optional[Dict] = None,
    ) -> List[RetrievedItem]:
        return []

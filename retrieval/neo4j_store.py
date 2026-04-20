"""Neo4j graph store scaffold"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class GraphEvidence:
    evidence_id: str
    text: str
    metadata: Dict
    score: float


class Neo4jStore:
    """Placeholder wrapper for graph queries"""

    def __init__(self, uri: str, username: str, password: str) -> None:
        self.uri = uri
        self.username = username
        self.password = password

    def upsert_service_graph(self, services: List[Dict]) -> int:
        return 0

    def query_neighbors(self, service: str, hops: int = 2) -> List[GraphEvidence]:
        return []

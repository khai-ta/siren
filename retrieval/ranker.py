"""Hybrid ranker scaffold"""

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class RankedEvidence:
    evidence_id: str
    text: str
    metadata: Dict
    source: str
    base_score: float
    fused_score: float = 0.0


def reciprocal_rank_fusion(
    ranked_lists: Dict[str, List[RankedEvidence]],
    k: int = 60,
    limit: int = 12,
) -> List[RankedEvidence]:
    return []

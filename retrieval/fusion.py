"""Reciprocal rank fusion"""

from typing import Dict, List


def reciprocal_rank_fusion(
    result_lists: List[List[Dict]],
    k: int = 60,
    top_n: int = 50,
) -> List[Dict]:
    """Each item's score = sum(1 / (k + rank_in_list_i)) across all lists"""
    scores: Dict[str, float] = {}
    items: Dict[str, Dict] = {}
    for result_list in result_lists:
        for rank, item in enumerate(result_list):
            item_id = item["id"]
            score = 1.0 / (k + rank + 1)
            scores[item_id] = scores.get(item_id, 0.0) + score
            items[item_id] = item

    ranked_ids = sorted(scores.keys(), key=lambda item_id: -scores[item_id])[:top_n]
    return [{**items[item_id], "fusion_score": scores[item_id]} for item_id in ranked_ids]

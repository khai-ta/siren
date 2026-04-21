from typing import List, Dict
from .store import FeedbackStore


def compute_accuracy_trend(store: FeedbackStore) -> List[Dict]:
    """Return daily accuracy percentages for the last N days"""
    investigations = store.list_investigations(limit=1000)

    # Bucket by day
    buckets: Dict[str, Dict[str, int]] = {}
    for inv in investigations:
        day = inv["created_at"].strftime("%Y-%m-%d")
        if day not in buckets:
            buckets[day] = {"correct": 0, "total": 0}

        if inv.get("verdict"):
            buckets[day]["total"] += 1
            if inv["verdict"] == "correct":
                buckets[day]["correct"] += 1

    trend = []
    for day, counts in sorted(buckets.items()):
        if counts["total"] > 0:
            trend.append({
                "date": day,
                "accuracy": counts["correct"] / counts["total"],
                "sample_size": counts["total"],
            })
    return trend


def compute_confidence_calibration(store: FeedbackStore) -> List[Dict]:
    """Compare predicted confidence against actual correctness"""
    investigations = store.list_investigations(limit=1000)

    # Bucket by confidence decile
    buckets = {i/10: {"correct": 0, "total": 0} for i in range(0, 11)}

    for inv in investigations:
        if not inv.get("verdict"):
            continue
        bucket = round(inv["reported_confidence"] * 10) / 10
        if bucket in buckets:
            buckets[bucket]["total"] += 1
            if inv["verdict"] == "correct":
                buckets[bucket]["correct"] += 1

    return [
        {
            "confidence": conf,
            "actual_accuracy": counts["correct"] / counts["total"] if counts["total"] else None,
            "sample_size": counts["total"],
        }
        for conf, counts in buckets.items()
        if counts["total"] > 0
    ]


def compute_source_effectiveness(store: FeedbackStore) -> List[Dict]:
    """Which evidence sources appear most often in correct investigations"""
    investigations = store.list_investigations(limit=1000)

    source_correct = {}
    source_total = {}

    for inv in investigations:
        if not inv.get("verdict"):
            continue

        # Extract sources from tool_history
        for tool_call in inv.get("tool_history", []):
            source = tool_call["tool_name"]
            source_total[source] = source_total.get(source, 0) + 1
            if inv["verdict"] == "correct":
                source_correct[source] = source_correct.get(source, 0) + 1

    return [
        {
            "source": source,
            "usage_count": total,
            "success_rate": source_correct.get(source, 0) / total,
        }
        for source, total in source_total.items()
    ]

from datetime import datetime, timedelta
from collections import defaultdict
from feedback.store import FeedbackStore


def compute_accuracy_trend(store: FeedbackStore, days: int = 30) -> list[dict]:
    """Compute daily accuracy trend over the past N days

    Returns list of dicts with keys: date, accuracy, total, correct
    """
    cutoff = datetime.now(datetime.now().astimezone().tzinfo) - timedelta(days=days)
    investigations = store.list_investigations(limit=10000)
    
    daily = defaultdict(lambda: {"total": 0, "correct": 0})
    
    for inv in investigations:
        if not inv.get("created_at"):
            continue
        created = inv["created_at"]
        if created < cutoff:
            continue
        
        date_key = created.date().isoformat()
        daily[date_key]["total"] += 1
        
        if inv.get("verdict") == "correct":
            daily[date_key]["correct"] += 1
    
    trend = []
    for date_str in sorted(daily.keys()):
        counts = daily[date_str]
        trend.append({
            "date": date_str,
            "accuracy": counts["correct"] / counts["total"] if counts["total"] > 0 else 0,
            "total": counts["total"],
            "correct": counts["correct"],
        })
    
    return trend if trend else None


def compute_confidence_calibration(store: FeedbackStore) -> list[dict]:
    """Analyze confidence calibration: does Siren's confidence match actual accuracy

    Groups verdicts by confidence bucket and compares predicted vs actual accuracy
    Returns list of dicts with keys: confidence, actual_accuracy, sample_size
    """
    investigations = store.list_investigations(limit=10000)

    # Group by confidence level (bucketed)
    buckets = defaultdict(lambda: {"correct": 0, "total": 0})

    for inv in investigations:
        if not inv.get("reported_confidence") or not inv.get("verdict"):
            continue

        # Bucket confidence into 10% ranges
        conf = inv["reported_confidence"]
        bucket = round(conf * 10) / 10

        buckets[bucket]["total"] += 1
        if inv["verdict"] == "correct":
            buckets[bucket]["correct"] += 1

    calib = []
    for confidence in sorted(buckets.keys()):
        counts = buckets[confidence]
        calib.append({
            "confidence": confidence,
            "actual_accuracy": counts["correct"] / counts["total"] if counts["total"] > 0 else 0,
            "sample_size": counts["total"],
        })

    return calib if calib else None


def compute_source_effectiveness(store: FeedbackStore) -> list[dict]:
    """Analyze which retrieval sources are most effective

    For each source, compute success rate (how often it leads to correct diagnosis)
    Returns list of dicts with keys: source, success_rate, total_uses

    Placeholder for Slice 5B - full implementation will extract source info from tool_history
    """
    # Stub: return empty for now
    return []

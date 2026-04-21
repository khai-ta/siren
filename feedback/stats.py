from datetime import datetime, timedelta
from collections import defaultdict
from feedback.store import FeedbackStore


def compute_accuracy_trend(store: FeedbackStore, days: int = 30) -> list[dict]:
    """Compute daily accuracy trend over the past N days.
    
    Returns list of dicts with keys: date, accuracy, total, correct.
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

"""Measure token savings from the 4 ROI optimizations"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Measure prompt size without initializing agent infrastructure
def estimate_tokens(text: str) -> int:
    """Rough estimate: 4 chars per token"""
    return len(text) // 4


def test_baseline_prompt():
    """Test current 97% baseline prompt format"""
    # Simulate investigator prompt at step 10 (lots of history)
    prompt = """Anomalies:
- database latency_p99 z=8.5
- auth-service error_rate z=5.2
- api-gateway latency_p99 z=4.1

Hypotheses:
? database query timeout causing downstream latency (conf 70%, 2for/0against)
? database lock contention from concurrent writes (conf 50%, 1for/0against)
✗ recent deployment introduced slow query (conf 30%, 0for/1against)
✗ memory exhaustion on database instance (conf 20%, 0for/1against)

Recent tools:
(steps 1-8 elided)
Step 9: query_logs → returned list[5]
Step 10: get_metrics → latency_p99 30ms->245ms (8.1x), error_rate 0.1%->1.2%

Prior evidence gathered: get_metrics (step 1), query_logs (step 2), get_dependencies (step 3)

Recent evidence:
  [ev_8] step 8 search_runbook: dict with keys: content, source, score
  [ev_9] step 9 query_logs: list[5]
  [ev_10] step 10 get_metrics: latency_p99 30ms->245ms (8.1x), error_rate 0.1%->1.2%

Plan:
- Verify database latency spike by checking metrics
- Inspect database query logs for timeouts
- Check database lock contention and deadlocks
- Review recent database schema changes or deployments

Step 11/15 (4 remaining)"""

    baseline_tokens = estimate_tokens(prompt)
    print("\n97% BASELINE PROMPT (step 10):")
    print(f"Size: {baseline_tokens} tokens\n")
    return baseline_tokens


def test_with_4_roi_optimizations():
    """Test prompt with 4 ROI optimizations applied"""
    # Same prompt but with optimizations:
    # 1. Plan only in steps <=3 (excluded at step 10)
    # 2. Only show open hypotheses (exclude rejected ones)
    # 3. Tool arguments compressed (already done - just result_summary shown)
    # 4. Evidence ledger keys cleanup (already done - no redundant keys)
    prompt = """Anomalies:
- database latency_p99 z=8.5
- auth-service error_rate z=5.2
- api-gateway latency_p99 z=4.1

Hypotheses:
? database query timeout causing downstream latency (conf 70%, 2for/0against)
? database lock contention from concurrent writes (conf 50%, 1for/0against)

Recent tools:
(steps 1-8 elided)
Step 9: query_logs → returned list[5]
Step 10: get_metrics → latency_p99 30ms->245ms (8.1x), error_rate 0.1%->1.2%

Prior evidence gathered: get_metrics (step 1), query_logs (step 2), get_dependencies (step 3)

Recent evidence:
  [ev_8] step 8 search_runbook: dict with keys: content, source, score
  [ev_9] step 9 query_logs: list[5]
  [ev_10] step 10 get_metrics: latency_p99 30ms->245ms (8.1x), error_rate 0.1%->1.2%

Step 11/15 (4 remaining)"""

    optimized_tokens = estimate_tokens(prompt)
    print("WITH 4 ROI OPTIMIZATIONS (step 10):")
    print(f"Size: {optimized_tokens} tokens\n")
    return optimized_tokens


if __name__ == "__main__":
    baseline = test_baseline_prompt()
    optimized = test_with_4_roi_optimizations()
    savings = baseline - optimized
    savings_pct = (savings / baseline) * 100

    print("=" * 70)
    print(f"Savings from 4 ROI optimizations:")
    print(f"  {baseline} -> {optimized} tokens")
    print(f"  -{savings} tokens ({savings_pct:.1f}% reduction)")
    print(f"\nAcross 15-step investigation: ~{savings * 15} tokens saved")
    print(f"Log compression (97%) + ROI optimizations (~{savings_pct:.0f}%) = combined impact")

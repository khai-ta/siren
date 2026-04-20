# Recommendation Service

## Overview
Recommendation Service computes personalized suggestions and ranking responses for user-facing surfaces. It runs with comparatively high baseline latency and memory footprint due to feature retrieval and scoring logic. Its health depends on efficient cache usage and stable fallback behavior to database.

## Dependencies
- Upstream callers: api-gateway
- Downstream: cache, database

## Key Metrics & Alert Thresholds
- error_rate: normal < 0.5%, warn > 2%, critical > 5%
- latency_p99: normal < 320ms, warn > 400ms, critical > 600ms
- cpu_pct: normal < 60%, warn > 75%, critical > 90%
- memory_pct: normal < 70%, warn > 85%, critical > 95%

## Common Failure Modes

### memory_leak
**Symptoms:** memory_pct trends upward for an extended window, then latency_p99 and error_rate accelerate once pods approach high memory pressure. Pod-level imbalance is common with one instance degrading first.
**Likely cause:** retained feature vectors, unbounded caches, or long-lived object growth in ranking workers.
**Remediation:** recycle affected pods, cap in-process cache growth, and inspect recent release diffs for retention regressions.

### cache_eviction_storm
**Symptoms:** cache hit rate drops while recommendation latency rises and fallback queries to database increase. Error_rate often rises later, after fallback load saturates downstream dependencies.
**Likely cause:** eviction churn on hot keys or insufficient cache capacity for active working set.
**Remediation:** increase effective cache headroom, prioritize hot-key warming, and throttle non-essential recommendation refresh paths.

### cascading_timeout
**Symptoms:** timeout logs and slow downstream read traces appear during upstream incidents, with gateway-facing latency becoming consistently elevated. Recommendation calls complete too late for responsive UX.
**Likely cause:** database or cache dependency slowdown propagates through synchronous request path.
**Remediation:** reduce fan-out depth, tighten timeout hierarchy, and restore primary downstream bottleneck before raising traffic limits.

## On-call Escalation
If automated remediation fails, escalate to the personalization team.

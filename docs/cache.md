# Cache

## Overview
Cache provides low-latency hot data access for auth and recommendation paths, reducing direct pressure on database. It handles the highest request volume in the platform and must remain stable under burst traffic. Cache degradation often appears first as higher miss rate and only later as downstream database saturation.

## Dependencies
- Upstream callers: auth-service, recommendation-service
- Downstream: none

## Key Metrics & Alert Thresholds
- error_rate: normal < 0.5%, warn > 2%, critical > 5%
- latency_p99: normal < 12ms, warn > 25ms, critical > 40ms
- cpu_pct: normal < 60%, warn > 75%, critical > 90%
- memory_pct: normal < 70%, warn > 85%, critical > 95%

## Common Failure Modes

### cache_eviction_storm
**Symptoms:** eviction and miss indicators climb while latency_p99 drifts upward and caller fallback traffic to database rises. Eventually error_rate increases once downstream paths saturate.
**Likely cause:** working set exceeds cache capacity or key churn invalidates hot entries too quickly.
**Remediation:** raise effective cache headroom, tune eviction policy for workload shape, and warm critical keys for auth and recommendation paths.

### memory_leak (Secondary Spillover)
**Symptoms:** recommendation-service memory leak increases request amplification and fallback behavior, causing cache caller pressure and noisier cache latency. Cache error rate may stay near baseline while client-facing services degrade.
**Likely cause:** simulator memory_leak originates in recommendation-service and drives secondary stress into shared cache access paths.
**Remediation:** stabilize recommendation-service first, then rebalance cache traffic and validate hit-rate recovery before removing mitigations.

### network_spike (Secondary Spillover)
**Symptoms:** auth-service and recommendation-service experience network-spike latency and produce burstier cache access, which appears as short-lived cache p99 jitter. Cache itself usually does not become the primary failing node.
**Likely cause:** simulator network_spike originates at api-gateway and immediate dependencies, creating indirect load volatility at cache callers.
**Remediation:** mitigate caller-side retries and concurrency first, then confirm cache metrics return to baseline as upstream network conditions recover.

## On-call Escalation
If automated remediation fails, escalate to the caching team.

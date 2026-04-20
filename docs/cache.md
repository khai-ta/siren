# Cache

## Overview
The cache accelerates reads for auth-service and recommendation-service in AcmeCloud. It absorbs hot-key traffic and protects the database from repeated lookups, so cache instability often shows up indirectly as a surge in database pressure

## Dependencies
- Upstream callers: auth-service, recommendation-service
- Downstream dependencies: none

## Key Metrics & Alert Thresholds
- error_rate: normal < 0.5%, warn > 2%, critical > 5%
- latency_p99: normal < 15ms, warn > 30ms, critical > 50ms
- cpu_pct: normal < 60%, warn > 75%, critical > 90%
- memory_pct: normal < 70%, warn > 85%, critical > 95%

## Common Failure Modes

### Cache Eviction Storm
**Symptoms:** Hit rate collapses, eviction logs spike, and upstream services begin falling back to database reads. Error rate may still look moderate at first while latency climbs rapidly
**Likely cause:** The working set is larger than the cache or key churn is too high
**Remediation:** Increase capacity, tune eviction policy, and reduce churn from the hottest callers

### Memory Leak
**Symptoms:** Memory usage rises gradually until eviction pressure becomes unstable, and one pod may become the clear outlier. Logs can look normal until the cache starts thrashing
**Likely cause:** Leaked in-memory structures or an oversized local cache segment
**Remediation:** Restart the offending instance, limit retained state, and verify the recent rollout

### Network Spike
**Symptoms:** Cache latency becomes erratic, but outright errors remain low. Downstream services may see more fallback traffic even though the cache itself appears mostly alive
**Likely cause:** Short-lived network instability between cache clients and cache nodes
**Remediation:** Check client timeouts, move traffic away from degraded nodes, and confirm no AZ-level network issue is in progress

## On-call Escalation
If automated remediation fails, escalate to the platform caching team.

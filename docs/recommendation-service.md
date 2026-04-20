# Recommendation Service

## Overview
Recommendation service enriches the user experience by computing personalized suggestions in AcmeCloud. It depends heavily on cache and database reads, so latency often moves with backend efficiency and cache health

## Dependencies
- Upstream callers: api-gateway, homepage rendering, recommendation APIs
- Downstream dependencies: cache, database

## Key Metrics & Alert Thresholds
- error_rate: normal < 0.5%, warn > 2%, critical > 5%
- latency_p99: normal < 320ms, warn > 500ms, critical > 750ms
- cpu_pct: normal < 60%, warn > 75%, critical > 90%
- memory_pct: normal < 70%, warn > 85%, critical > 95%

## Common Failure Modes

### Cache Eviction Storm
**Symptoms:** Cache hit rate falls, recommendation p99 grows quickly, and logs mention falling back to database. Error rate may rise only after the fallback path becomes saturated
**Likely cause:** The cache is evicting hot keys or is too small for the current working set
**Remediation:** Increase cache capacity if possible, reduce churn, and warm the hottest keys before restoring normal traffic

### Memory Leak
**Symptoms:** Memory rises gradually, latency gets worse before errors appear, and a single pod can look much worse than the rest. Logs may show timeout bursts or queueing delays in the hottest instance
**Likely cause:** Leaked feature objects, caches, or request state in a long-lived worker
**Remediation:** Restart the affected pod, isolate it from traffic, and inspect recent releases for retained in-memory data

### Cascading Timeout
**Symptoms:** p99 inflates sharply when database latency climbs, and the gateway starts seeing slow recommendation responses. The service may still return responses, but they arrive too late to be useful
**Likely cause:** Downstream database saturation or retry amplification
**Remediation:** Reduce concurrency, lower retries, and verify whether database or cache is the primary bottleneck

## On-call Escalation
If automated remediation fails, escalate to the personalization platform team.

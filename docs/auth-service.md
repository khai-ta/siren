# Auth Service

## Overview
Auth service validates identities, issues tokens, and protects user-facing workflows in AcmeCloud. It depends on fast database and cache access, so small upstream slowdowns can quickly turn into login failures or token validation timeouts.

## Dependencies
- Upstream callers: api-gateway, admin tooling, and other services that need identity checks
- Downstream dependencies: database, cache

## Key Metrics & Alert Thresholds
- error_rate: normal < 0.5%, warn > 2%, critical > 5%
- latency_p99: normal < 90ms, warn > 150ms, critical > 225ms
- cpu_pct: normal < 60%, warn > 75%, critical > 90%
- memory_pct: normal < 70%, warn > 85%, critical > 95%

## Common Failure Modes

### Cascading Timeout
**Symptoms:** Token validation p99 rises first, then 5xx responses and database timeout logs follow. Auth-service is often one of the earliest downstream services to show pain when the database starts slowing down.
**Likely cause:** Slow database reads spread into auth lookups, and retries multiply the delay.
**Remediation:** Reduce auth retries, enable a short-lived fallback for low-risk reads if policy allows, and verify database health before restoring traffic.

### Memory Leak
**Symptoms:** Memory climbs over time, GC pauses get longer, and p99 latency drifts up before error rate spikes. A single pod may look noticeably worse than the rest.
**Likely cause:** Leaked session state, caches, or token-processing objects in a long-lived pod.
**Remediation:** Restart the affected pod, isolate the bad instance, and review recent code or config changes for retained objects or unbounded caches.

### Network Spike
**Symptoms:** Sporadic timeouts and moderate p99 growth, usually during login bursts or token refresh traffic. Error rate may stay moderate even while users feel the impact.
**Likely cause:** Short network instability between auth-service and database or cache.
**Remediation:** Check network path health, lower retry pressure, and shift traffic away from unstable nodes.

## On-call Escalation
If automated remediation fails, escalate to the identity platform team.

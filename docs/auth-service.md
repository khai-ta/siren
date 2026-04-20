# Auth Service

## Overview
Auth Service validates credentials, issues tokens, and enforces identity checks for user-facing flows. It serves high request volume behind the gateway and depends on low-latency lookups in cache and database. Degradation here quickly converts into login failures and token timeout symptoms.

## Dependencies
- Upstream callers: api-gateway
- Downstream: database, cache

## Key Metrics & Alert Thresholds
- error_rate: normal < 0.5%, warn > 2%, critical > 5%
- latency_p99: normal < 80ms, warn > 130ms, critical > 210ms
- cpu_pct: normal < 60%, warn > 75%, critical > 90%
- memory_pct: normal < 70%, warn > 85%, critical > 95%

## Common Failure Modes

### cascading_timeout
**Symptoms:** token validation latency climbs, then error_rate follows with repeated database timeout logs. Gateway requests to auth paths accumulate while retries increase backend pressure.
**Likely cause:** database latency incident propagates into auth request chains.
**Remediation:** lower retry concurrency, shorten timeout ceilings, and verify database saturation before restoring full auth traffic.

### cache_eviction_storm
**Symptoms:** cache miss rate rises and auth p99 increases as more requests fall back to database reads. Error rate may rise later once database pressure reaches a tipping point.
**Likely cause:** hot-key churn or undersized cache causes widespread key eviction.
**Remediation:** stabilize cache capacity, pre-warm critical auth keys, and reduce high-cardinality cache writes until hit rate normalizes.

### network_spike
**Symptoms:** intermittent timeout bursts appear between auth pods and cache or database with uneven pod-level latency. Client login responsiveness becomes inconsistent without a uniform hard outage.
**Likely cause:** transient packet loss or node-level network jitter.
**Remediation:** move traffic off unstable nodes, tighten connection pool failover behavior, and validate zone-level network health.

## On-call Escalation
If automated remediation fails, escalate to the identity team.

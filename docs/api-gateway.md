# API Gateway

## Overview
The API Gateway is the front door for AcmeCloud traffic. It routes requests to auth-service, recommendation-service, and payment-service, so it is usually the first place users feel downstream trouble

## Dependencies
- Upstream callers: external clients, web apps, mobile apps, partner integrations
- Downstream dependencies: auth-service, recommendation-service, payment-service

## Key Metrics & Alert Thresholds
- error_rate: normal < 0.5%, warn > 2%, critical > 5%
- latency_p99: normal < 70ms, warn > 120ms, critical > 180ms
- cpu_pct: normal < 60%, warn > 75%, critical > 90%
- memory_pct: normal < 70%, warn > 85%, critical > 95%

## Common Failure Modes

### Cascading Timeout
**Symptoms:** Gateway p99 climbs sharply, 5xx responses rise, and queues begin to grow. Logs often show upstream timeouts from auth-service or payment-service, with retries driving more load
**Likely cause:** A downstream service is slow or unavailable, and the gateway is amplifying the problem by waiting too long or retrying too often
**Remediation:** Reduce gateway timeout budgets, cap retries, and shed load from non-critical routes. Check auth-service, payment-service, and database health before restoring traffic

### Bad Deployment
**Symptoms:** Error rate jumps on one route while other routes stay mostly healthy. Deployment-related errors or sudden 4xx/5xx bursts usually appear alongside a narrow latency increase
**Likely cause:** A rollout introduced a routing, auth, or serialization bug in the gateway path
**Remediation:** Roll back the deployment, compare request and response diffs, and verify config changes before re-enabling traffic

### Network Spike
**Symptoms:** Latency rises across many endpoints with a moderate increase in timeouts, while error rate may stay comparatively low. Retries, queue depth, and client backoff often rise at the same time
**Likely cause:** Intermittent network instability or packet loss between the gateway and upstream services
**Remediation:** Confirm network health, reduce retry concurrency, and move traffic away from affected nodes or zones

## On-call Escalation
If automated remediation fails, escalate to the platform team.

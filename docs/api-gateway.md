# API Gateway

## Overview
API Gateway is the entry point for client traffic. It applies edge policies and fans calls to auth-service, recommendation-service, and payment-service. Because it sits at the edge, it often shows incidents first.

## Dependencies
- Upstream callers: none (edge ingress in simulator topology)
- Downstream: auth-service, recommendation-service, payment-service

## Key Metrics & Alert Thresholds
- error_rate: normal < 0.5%, warn > 2%, critical > 5%
- latency_p99: normal < 60ms, warn > 90ms, critical > 150ms
- cpu_pct: normal < 60%, warn > 75%, critical > 90%
- memory_pct: normal < 70%, warn > 85%, critical > 95%

## Common Failure Modes

### network_spike
**Symptoms:** latency_p99 rises across most routes and timeout logs increase from downstream calls. Error rate can stay moderate while client-perceived slowness jumps.
**Likely cause:** short-lived network instability between gateway pods and downstream service endpoints.
**Remediation:** reduce retry fan-out, enable route-level load shedding for non-critical paths, and rebalance traffic away from degraded nodes or zones.

### cascading_timeout
**Symptoms:** 5xx responses rise with repeated upstream timeout messages, especially toward auth-service and payment-service. Queueing increases and latency remains high.
**Likely cause:** downstream saturation propagates to the gateway, which amplifies impact through concurrent waits and retries.
**Remediation:** tighten timeout budgets, cap retries, and temporarily rate-limit high-cost routes while validating health of auth-service, payment-service, and database dependencies.

### database_lock
**Symptoms:** gateway timeout and 5xx rates increase after auth-service, payment-service, and recommendation-service report lock wait or database timeout errors. User-facing routes degrade broadly.
**Likely cause:** lock contention in database propagates through dependent services and surfaces at the edge.
**Remediation:** prioritize recovery of database and dependent services, keep gateway retry limits tight, and enable temporary load shedding until downstream latency normalizes.

### memory_leak (Secondary Spillover)
**Symptoms:** recommendation-service tail latency rises first, then gateway p99 and timeout rate climb on recommendation-heavy routes.
**Likely cause:** simulator memory_leak originates in recommendation-service and reaches the gateway as downstream slowness.
**Remediation:** stabilize recommendation-service pods, keep gateway retry budgets low, and isolate slow recommendation paths until pressure clears.

### cache_eviction_storm (Secondary Spillover)
**Symptoms:** bursty fallback traffic from auth-service and recommendation-service causes intermittent gateway latency spikes and route-level 5xx growth.
**Likely cause:** simulator cache_eviction_storm increases cache misses and database fallback, creating edge-level latency amplification.
**Remediation:** reduce non-critical route load, coordinate cache warm-up and caller backoff, and remove mitigations after hit rate recovers.

## On-call Escalation
If automated remediation fails, escalate to the platform edge team.

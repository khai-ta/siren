# Message Queue

## Overview
Message Queue buffers asynchronous workload, smoothing burst traffic from payment and other producers. It protects synchronous request paths from transient spikes by absorbing work and draining through consumers. When unhealthy, it manifests as lag growth and delayed business completion rather than immediate hard errors.

## Dependencies
- Upstream callers: payment-service
- Downstream: none

## Key Metrics & Alert Thresholds
- error_rate: normal < 0.5%, warn > 2%, critical > 5%
- latency_p99: normal < 30ms, warn > 60ms, critical > 100ms
- cpu_pct: normal < 60%, warn > 75%, critical > 90%
- memory_pct: normal < 70%, warn > 85%, critical > 95%

## Common Failure Modes

### bad_deployment
**Symptoms:** consumer error logs surge right after rollout, queue lag rises, and dead-letter growth accelerates for specific partitions or schemas. Producer rate remains near baseline while processing throughput drops.
**Likely cause:** simulator bad_deployment originates in payment-service and creates malformed or retry-heavy producer behavior that destabilizes queue consumers.
**Remediation:** roll back payment-service deployment, isolate affected message streams, and resume consumer replay only after producer payloads are validated.

### network_spike
**Symptoms:** broker round-trip latency becomes erratic, with intermittent publish or consume timeouts and unstable acknowledgement times. Queue depth oscillates as consumers reconnect.
**Likely cause:** simulator network_spike starts at api-gateway and immediate dependencies, and queue impact appears secondarily through payment-service retry and ack jitter.
**Remediation:** dampen payment-service retry pressure, apply producer backoff, and verify broker health before increasing producer throughput.

### cascading_timeout
**Symptoms:** downstream services process messages too slowly, causing sustained lag increase and delayed completion of payment side effects. Error rate may stay moderate while latency-related SLOs fail.
**Likely cause:** simulator cascading_timeout and database_lock incidents saturate database paths, slowing payment-driven consumers and increasing queue lag.
**Remediation:** apply producer backpressure, prioritize critical queues, and restore the degraded downstream dependency before draining backlog.

## On-call Escalation
If automated remediation fails, escalate to the messaging team.

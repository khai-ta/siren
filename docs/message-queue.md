# Message Queue

## Overview
The message queue buffers asynchronous work in AcmeCloud, especially payment side effects and delayed downstream processing. It protects the system from bursty producers, but backlog growth can quickly affect user-visible completion times

## Dependencies
- Upstream callers: payment-service, asynchronous job producers
- Downstream dependencies: none

## Key Metrics & Alert Thresholds
- error_rate: normal < 0.5%, warn > 2%, critical > 5%
- latency_p99: normal < 35ms, warn > 70ms, critical > 110ms
- cpu_pct: normal < 60%, warn > 75%, critical > 90%
- memory_pct: normal < 70%, warn > 85%, critical > 95%

## Common Failure Modes

### Retry Storm
**Symptoms:** Queue depth rises unexpectedly, consumers fall behind, and the payment path starts timing out while waiting for async confirmation. Logs often show repeated deliveries or dead-letter growth
**Likely cause:** Producers are retrying too aggressively after downstream failures
**Remediation:** Cap retries, slow the offending producer, and drain or isolate poison messages before resuming normal flow

### Bad Deployment
**Symptoms:** Consumer failures appear immediately after rollout, often with narrow scope to one consumer group or queue partition. The queue itself may look healthy until processing lag becomes visible
**Likely cause:** A faulty consumer release or schema mismatch
**Remediation:** Roll back, compare message schemas, and restart only the affected consumers once the issue is understood

### Cascading Timeout
**Symptoms:** Queue depth grows because downstream services are too slow to acknowledge work, and the backlog amplifies the delay for everything behind it. Error rate may remain modest while user-perceived latency degrades sharply
**Likely cause:** A downstream bottleneck, often in database or payment processing
**Remediation:** Reduce producer rate, add backpressure, and restore the slow downstream dependency before clearing the queue

## On-call Escalation
If automated remediation fails, escalate to the messaging platform team.

# Payment Service

## Overview
Payment service executes purchase flows and writes transaction state for AcmeCloud. It is one of the most sensitive services in the transaction path because small latency spikes can quickly cascade into visible failures or abandoned requests

## Dependencies
- Upstream callers: api-gateway, checkout flows, partner billing integrations
- Downstream dependencies: database, message-queue

## Key Metrics & Alert Thresholds
- error_rate: normal < 0.5%, warn > 2%, critical > 5%
- latency_p99: normal < 150ms, warn > 220ms, critical > 330ms
- cpu_pct: normal < 60%, warn > 75%, critical > 90%
- memory_pct: normal < 70%, warn > 85%, critical > 95%

## Common Failure Modes

### Bad Deployment
**Symptoms:** Payment errors jump quickly after a rollout, while the gateway may still look healthy on unrelated routes. Logs often show rollback messages or downstream write failures concentrated in one pod
**Likely cause:** A logic bug or schema mismatch in the payment release
**Remediation:** Roll back immediately, compare release artifacts, and replay a small set of safe transactions before re-enabling full traffic

### Database Lock Contention
**Symptoms:** p99 latency and error rate spike together, with logs pointing to lock waits, deadlocks, or exhausted connection pools. Retry traffic makes the incident look worse than the initial lock event
**Likely cause:** A long-running transaction or hot row lock in the database
**Remediation:** Identify the blocking transaction, kill or roll it back if safe, and reduce retry pressure until the lock clears

### Retry Storm
**Symptoms:** RPS spikes on the database side even though external traffic has not increased. Payment-service may show repeated attempts and the queue may grow faster than consumer throughput
**Likely cause:** Client and gateway retry loops are amplifying a downstream failure
**Remediation:** Cap retries, add jitter, and throttle the hottest payment paths until the downstream service stabilizes

## On-call Escalation
If automated remediation fails, escalate to the payments platform team.

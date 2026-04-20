# Database

## Overview
The database is the shared persistence layer for AcmeCloud transactions, sessions, and recommendation lookups. Because so many services depend on it, even a localized slowdown can ripple across the platform very quickly

## Dependencies
- Upstream callers: auth-service, payment-service, recommendation-service
- Downstream dependencies: none

## Key Metrics & Alert Thresholds
- error_rate: normal < 0.5%, warn > 2%, critical > 5%
- latency_p99: normal < 45ms, warn > 90ms, critical > 150ms
- cpu_pct: normal < 60%, warn > 75%, critical > 90%
- memory_pct: normal < 70%, warn > 85%, critical > 95%

## Common Failure Modes

### Database Lock Contention
**Symptoms:** Lock wait errors rise fast, p99 spikes dramatically, and connection pools get exhausted. Upstream logs usually show a mix of timeouts and retries as auth, payment, and recommendation services wait on the same hot rows
**Likely cause:** A lock-heavy transaction, schema migration, or long-running query is blocking critical rows
**Remediation:** Identify the blocker, roll back or terminate it if safe, and reduce write pressure until the lock clears

### Cascading Timeout
**Symptoms:** Database p99 and error rate jump together, followed by a broad increase in errors across the dependent services. The service can look like a single bottleneck even though the blast radius is platform-wide
**Likely cause:** Saturation or slow queries cause callers to pile up and retry
**Remediation:** Stop or slow the hottest callers, inspect slow query logs, and restore capacity before lifting throttles

### Retry Storm
**Symptoms:** RPS on the database climbs far beyond normal traffic while latency stays high. The database may not be receiving more user demand, only more retry attempts
**Likely cause:** Auth or payment paths are retrying on timeout and multiplying load
**Remediation:** Tighten retry budgets, add jittered backoff, and cut off pathological callers until the backlog drains

## On-call Escalation
If automated remediation fails, escalate to the database platform team.

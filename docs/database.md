# Database

## Overview
Database is the shared system of record for transactional and identity data across the platform. It serves multiple latency-sensitive call paths simultaneously, including auth, payment, and recommendation workloads. Because many critical services depend on it, small degradations can create large cross-service blast radius.

## Dependencies
- Upstream callers: auth-service, payment-service, recommendation-service
- Downstream: none

## Key Metrics & Alert Thresholds
- error_rate: normal < 0.5%, warn > 2%, critical > 5%
- latency_p99: normal < 45ms, warn > 90ms, critical > 150ms
- cpu_pct: normal < 60%, warn > 75%, critical > 90%
- memory_pct: normal < 70%, warn > 85%, critical > 95%

## Common Failure Modes

### database_lock
**Symptoms:** lock wait and deadlock signals increase, latency_p99 spikes, and caller pools begin to exhaust connections. Dependent services show synchronized timeout patterns.
**Likely cause:** conflicting long-running transactions or hot-row contention from concurrent writes.
**Remediation:** identify and terminate or rollback blocking sessions when safe, reduce conflicting write concurrency, and defer non-critical migrations.

### cascading_timeout
**Symptoms:** elevated latency and timeout errors appear in database first, followed quickly by increased errors in auth-service, payment-service, and recommendation-service. End-user paths fail even when edge components look healthy.
**Likely cause:** query saturation and retry amplification from multiple callers.
**Remediation:** throttle highest-cost query paths, enforce stricter caller timeout and retry budgets, and recover capacity before restoring full throughput.

### memory_leak (Secondary Spillover)
**Symptoms:** recommendation-service memory growth is followed by sustained fallback read pressure and rising database tail latency during recommendation-heavy traffic windows.
**Likely cause:** simulator memory_leak begins in recommendation-service and increases dependency load on database through slower cache-effective processing.
**Remediation:** mitigate recommendation-service memory leak first, apply temporary query throttles for non-critical recommendation reads, and monitor latency normalization before rollback of controls.

## On-call Escalation
If automated remediation fails, escalate to the database team.

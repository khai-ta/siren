"""Static service topology and shared simulator constants"""

SERVICES = {
    "api-gateway": {"rps": 500, "error_rate": 0.001, "latency_p50": 12, "latency_p99": 45, "cpu": 30, "memory": 40},
    "auth-service": {"rps": 480, "error_rate": 0.002, "latency_p50": 18, "latency_p99": 60, "cpu": 25, "memory": 35},
    "payment-service": {"rps": 120, "error_rate": 0.001, "latency_p50": 35, "latency_p99": 110, "cpu": 20, "memory": 30},
    "recommendation-service": {"rps": 300, "error_rate": 0.003, "latency_p50": 80, "latency_p99": 250, "cpu": 45, "memory": 60},
    "database": {"rps": 600, "error_rate": 0.001, "latency_p50": 8, "latency_p99": 30, "cpu": 40, "memory": 70},
    "cache": {"rps": 900, "error_rate": 0.0005, "latency_p50": 2, "latency_p99": 8, "cpu": 15, "memory": 55},
    "message-queue": {"rps": 200, "error_rate": 0.001, "latency_p50": 5, "latency_p99": 20, "cpu": 10, "memory": 30},
}

DEPENDENCIES = {
    "api-gateway": ["auth-service", "recommendation-service", "payment-service"],
    "auth-service": ["database", "cache"],
    "payment-service": ["database", "message-queue"],
    "recommendation-service": ["cache", "database"],
    "database": [],
    "cache": [],
    "message-queue": [],
}


def hops_from_origin(service: str, origin: str) -> int:
    """Compute graph distance from origin service to given service using BFS.
    
    Used to calculate propagation delays for incident effects through service dependencies.
    """
    if service == origin:
        return 0
    
    visited = {origin}
    queue = [(origin, 0)]
    
    while queue:
        current, dist = queue.pop(0)
        neighbors = list(DEPENDENCIES.get(current, []))
        neighbors += [caller for caller, deps in DEPENDENCIES.items() if current in deps]
        
        for neighbor in neighbors:
            if neighbor == service:
                return dist + 1
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, dist + 1))
    
    return 999


INCIDENT_MULTIPLIERS = {
    "database": {"latency_p99": 8.0, "error_rate": 10.0},
    "auth-service": {"latency_p99": 4.0, "error_rate": 6.0},
    "payment-service": {"latency_p99": 3.0, "error_rate": 5.0},
    "recommendation-service": {"latency_p99": 2.0, "error_rate": 3.0},
    "api-gateway": {"latency_p99": 2.0, "error_rate": 4.0},
}

LOG_TEMPLATES = {
    "database": [
        "Query execution timeout after {duration}ms - table: orders",
        "Connection pool exhausted: 0 of {pool_size} connections available",
        "Lock wait timeout exceeded; try restarting transaction",
        "Slow query detected: SELECT * FROM transactions WHERE user_id=? ({duration}ms)",
    ],
    "auth-service": [
        "Upstream database call failed after {duration}ms - retrying (attempt {attempt}/3)",
        "Token validation timeout - database unreachable",
        "Circuit breaker OPEN: database error rate {error_pct}% exceeds threshold",
    ],
    "payment-service": [
        "Payment processing failed: database write timeout after {duration}ms",
        "Transaction rollback: upstream service unavailable",
        "Dead letter queue depth: {depth} - consumer falling behind",
    ],
    "recommendation-service": [
        "Memory usage at {memory_pct}% - GC pressure increasing",
        "Feature store query latency degraded: {duration}ms (expected <100ms)",
        "OOM risk: heap at {memory_pct}% - request queue starting to back up",
        "Cache miss rate elevated: {miss_pct}% - falling back to database",
        "Feature vector fetch timeout after {duration}ms",
    ],
    "api-gateway": [
        "Upstream timeout: auth-service failed to respond within {duration}ms",
        "503 Service Unavailable returned to client - downstream error rate {error_pct}%",
        "Request queue depth: {depth} - shedding load",
    ],
    "cache": [
        "Cache eviction rate elevated: {eviction_rate}/sec - memory pressure detected",
        "Cache miss storm: {miss_pct}% miss rate - falling back to database for all reads",
        "Cache memory usage at {memory_pct}% - evicting LRU keys aggressively",
        "Cache hit rate degraded to {hit_pct}% - upstream services experiencing elevated DB load",
    ],
    "message-queue": [
        "Queue depth nominal: {depth} messages",
    ],
}

METRIC_KEYS = ["rps", "error_rate", "latency_p50", "latency_p99", "cpu", "memory"]
ANOMALY_KEYS = ["error_rate", "latency_p99"]
ANOMALY_SERVICE_ORDER = {
    "database": 0,
    "auth-service": 1,
    "payment-service": 2,
    "recommendation-service": 3,
    "api-gateway": 4,
    "cache": 5,
    "message-queue": 6,
}

# Which edge is critical (if this dependency fails, it cascades)
CRITICAL_EDGES = {
    ("auth-service", "database"),
    ("payment-service", "database"),
    ("recommendation-service", "database"),
    ("api-gateway", "auth-service"),
    ("api-gateway", "payment-service"),
}


def get_downstream_services(service: str, visited: set = None) -> list:
    """Return all services transitively downstream of the given service"""
    if visited is None:
        visited = set()

    if service in visited:
        return []

    visited.add(service)

    callers = [caller for caller, deps in DEPENDENCIES.items() if service in deps]
    downstream = []

    for caller in callers:
        if caller == service or caller in downstream:
            continue
        downstream.append(caller)
        for nested in get_downstream_services(caller, visited):
            if nested != service and nested not in downstream:
                downstream.append(nested)

    return downstream

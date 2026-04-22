# SIREN: Autonomous Incident Investigation

Autonomous root cause analysis for distributed systems. SIREN detects anomalies in real-time metrics, investigates using multi-modal retrieval, and optimizes investigation quality through feedback-driven learning.

## Problem

Incident response is manual and inconsistent: engineers must correlate metrics across multiple systems, search logs, check dependencies, and construct RCAs often under time pressure with incomplete context. This scales poorly and produces unreliable conclusions.

SIREN automates this workflow: detect anomalies, investigate systematically using all available data sources, and learn from engineer feedback to improve future investigations.

## At a Glance

| Component | Purpose | Technology |
|-----------|---------|------------|
| **Detection** | Identify anomalies in metrics | Z-score + PELT changepoint, IsolationForest |
| **Investigation** | Autonomous root cause analysis | LangGraph agent, Claude LLM, multi-modal retrieval |
| **Learning** | Improve with feedback | Laplace-smoothed weight optimization, PostgreSQL |

**Performance:** 30-90s per incident, 30-50k tokens, ~$0.10-0.15 cost | **Accuracy:** 78-91% (improves with feedback)

## Architecture

```
Metrics → Detect (statistical + ML)
       → Anomalies[] + Incident{type, severity}
       → Investigate (LangGraph agent, 4 nodes, multi-modal retrieval)
       → RCA{root_cause, confidence, evidence, report}
       → Store + Feedback loop
       → Weight optimization → Faster/more accurate next investigation
```

Three independent components connected by clear contracts:

### 1. Detection (`detection/`)

Parallel statistical + ML detection, deduplication, incident classification.

**Input:** List[Dict] with timestamp, service, error_rate, latency_p99, latency_p50, rps, cpu, memory

**Components:**
- **Statistical** — Z-score (3.0σ default) + PELT changepoint on each metric per service
- **ML** — IsolationForest (contamination=0.05) trained on baseline rows
- **Classification** — Heuristic rules: memory>85% → "memory", latency+no_error → "timeout", etc.

**Output:**
```python
anomalies: List[{timestamp, service, metric, value, zscore, detector, changepoint}]
incident: {incident_id, affected_services, anomaly_type, severity}
```

**Trade-offs:**
- Baseline = first 30% rows (works well for incidents within 1-2h; fails for long-tail data)
- Z-score sensitive to distribution shape (assumes normality; skewed metrics underdetect)
- IsolationForest doesn't produce real z-scores (sentinel=-99.0)

### 2. Investigation (`agent/` + `retrieval/`)

LangGraph agentic system: Plan → Investigate → Verify → Report (max 15 steps, ~30-90s).

**Nodes:**
- **Plan** — Generate investigation steps from anomalies + origin_service (Haiku LLM, 2-3s)
- **Investigate** — Loop: call tool → analyze evidence → update hypotheses (Sonnet LLM, 20-60s for 5-7 tool calls)
- **Verify** — Challenge conclusion, adjust confidence (Haiku, 3-5s)
- **Report** — Generate markdown RCA with evidence citations (Sonnet, 2-3s)

**Tools** (all cached in Redis, 5min TTL):
- `query_logs(service, query, window)` → Pinecone vector search + Cohere reranking, weights applied
- `get_metrics(service, window)` → TimescaleDB baseline vs peak comparison
- `get_dependencies(service)` → Neo4j graph traversal
- `search_runbook(query)` → Doc vector search

**Input Contract:**
```python
anomalies: List[Dict]          # From detection layer
origin_service: str            # Primary service
window_start, window_end: str  # ISO timestamps (±5m from anomalies)
incident_type: str             # "compute"|"network"|"database"|"memory"|"timeout"
max_steps: int                 # Default 15 (range 1-30)
```

**Output Contract:**
```python
{
    final_root_cause: str,          # e.g., "database_connection_pool_exhaustion"
    final_confidence: float,        # 0.0 to 1.0
    final_report: str,              # Markdown RCA
    current_step: int,              # Steps taken
    tool_history: List,             # All tool calls + results
    evidence_ledger: Dict,          # Keyed evidence items
    hypotheses: List,               # Evolved hypotheses
}
```

**Bottlenecks:**
- Pinecone reranking latency (3-5s per query_logs call)
- LLM token limit for large log/metric volumes
- Redis/PostgreSQL query latency

### 3. Feedback (`feedback/`)

Engineer verdicts → weight optimization → improved future investigations.

**Flow:**
1. Store investigation result (PostgreSQL `investigations` table)
2. Engineer provides verdict: correct / partial / wrong
3. Store verdict (PostgreSQL `feedback` table)
4. Recompute (source, incident_type) → weight using: `weight = 0.5 + (correct+1)/(total+2)`
5. Apply weights in next investigation

**Formula Rationale:**
- Laplace smoothing (+1/+2): stabilizes small sample sizes, prevents extreme weights
- Range [0.5, 1.5]: penalizes poor sources (0.5x floor), caps excellent sources (1.5x ceiling)

**Components:**
- **Store** (`feedback/store.py`) — PostgreSQL persistence for investigations, verdicts, weights
- **Optimizer** (`feedback/optimizer.py`) — Weight computation from verdict data
- **Analytics** (`feedback/stats.py`) — Accuracy trends, confidence calibration, tool effectiveness

**Closed Loop:** Weights improve retrieval quality → more accurate investigations → better feedback → better weights

## Quick Start

### 1. Prerequisites & Setup

```bash
# Clone and install
git clone <repo>
cd siren
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env: ANTHROPIC_API_KEY, PINECONE_*, NEO4J_*, TIMESCALE_*, FEEDBACK_*
```

**Required Services:** PostgreSQL, Pinecone, TimescaleDB, Neo4j. Optional: Redis (caching). See `docs/SETUP.md` for Docker Compose setup.

### 2. Investigate an Incident

```bash
python investigate.py data/incidents/cascading_timeout/metrics.csv [--reindex]
```

**Output:** RCA saved to `data/reports/`, includes root cause, confidence, evidence, remediation steps.

Incident bundle structure:
```
data/incidents/cascading_timeout/
├── metrics.csv    (timestamp, service, error_rate, latency_p99, latency_p50, rps, cpu, memory)
├── logs.csv       (timestamp, service, level, message)
└── traces.csv     (optional)
```

### 3. Provide Feedback & Optimize

```bash
streamlit run dashboard/overview.py
```

1. Go to **Investigate** → select an incident → click "Analyze"
2. Review the investigation report and provide feedback in the form
3. Go to **History** → search and review past investigations
4. Go to **System Analysis** → click "Recompute weights" to optimize retrieval based on feedback

## Code Layout

```
detection/              Anomaly detection (statistical + ML)
agent/                  LangGraph investigation agent (4 nodes)
retrieval/              Multi-modal retrieval orchestration
feedback/               PostgreSQL + weight optimization
dashboard/              Streamlit UI
data/                   Incident bundles (gitignored)
docs/                   Setup, API, architecture guides, service runbooks
investigate.py          CLI entry point
```

## Concepts & Data Models

### Incident Types (auto-classified)

| Type | Pattern | Typical Remediation |
|------|---------|-------------------|
| **memory** | memory > 85% | Scale up, kill memory leaks |
| **timeout** | latency spike, no errors | Retry logic, timeout config |
| **compute** | error_rate + latency | Scale horizontally, optimize queries |
| **network** | latency + rps spike | Rate limiting, circuit breaker |
| **database** | error_rate spike | Connection pooling, query optimization |

Classification logic in `detection/trigger.py:classify_incident_type()`. Future: ML classifier trained on feedback verdicts.

### Data Contracts

**Anomaly** (detection output):
```python
{timestamp, service, metric, value, zscore, baseline_mean, baseline_std, detector, changepoint}
```

**Incident** (detection output):
```python
{incident_id, timestamp, affected_services[], anomaly_type, severity, triggering_metrics[]}
```

**Investigation State** (from agent.run.run_investigation()):
```python
{
    # Input
    incident_id, anomalies[], origin_service, incident_type, window_start, window_end,
    # Working memory
    investigation_plan[], current_step, hypotheses[], tool_history[], evidence_ledger{},
    # Output
    final_root_cause, final_confidence (0.0-1.0), final_report
}
```

**Retrieval Weights** (PostgreSQL retrieval_weights table):
```python
{source: str, incident_type: str, weight: float (0.5-1.5)}
```
Example: `("query_logs", "database") → 1.38x`

## Configuration

### Environment

See `docs/SETUP.md` for full backend setup (Docker Compose, Kubernetes).

**Required:**
```bash
ANTHROPIC_API_KEY=sk-ant-...
COHERE_API_KEY=...
PINECONE_API_KEY=pcsk_...
PINECONE_INDEX=siren-logs
NEO4J_URI=bolt://localhost:7687
NEO4J_AUTH=neo4j:password
FEEDBACK_URI=postgresql://postgres:password@localhost:5432/siren_feedback
TIMESCALE_URI=postgresql://postgres:password@localhost:5433/siren
```

**Optional:**
```bash
REDIS_URL=redis://localhost:6379            # Caching (5min TTL)
TOOL_CACHE_TTL=300
CHECKPOINT_URI=                              # Leave empty (no LangGraph checkpointing)
```

### Model Tuning

Edit `agent/nodes.py`:
- `_fast_llm`: Haiku for planning, hypothesis updates (cost optimization)
- `_reasoning_llm`: Sonnet for investigation, verification, reporting (quality)

## Usage

### CLI

```bash
python investigate.py data/incidents/incident/metrics.csv [--reindex]
```
Outputs markdown RCA. `--reindex` rebuilds Pinecone/TimescaleDB indices (use if backend data is stale).

### API

```python
from detection import detect; from agent.run import run_investigation
from feedback.store import FeedbackStore

metrics = [...]  # Load from CSV
anomalies, incident = detect(metrics)
result = run_investigation(
    anomalies, incident["affected_services"][0],
    anomalies[0]["timestamp"], anomalies[-1]["timestamp"],
    incident["incident_id"], incident["anomaly_type"])
    
store = FeedbackStore()
store.save_investigation(result, incident["anomaly_type"])
store.save_feedback(result["incident_id"], "correct")  # Feedback

from feedback.optimizer import RetrievalOptimizer
RetrievalOptimizer(store).recompute_weights()  # Optimize
```

See `docs/API_REFERENCE.md` for full signatures and examples.

### Dashboard

```bash
streamlit run dashboard/overview.py
```

**Pages:**
- **Overview** — Key metrics (total cases, reviewed count, accuracy), recent investigations table
- **Investigate** — Live incident analysis: select incident, run analysis, view results, report, topology, and provide feedback
- **History** — Past investigations with search/filter by date/type/root cause, view full investigation reports
- **Dependencies** — Service topology graph showing relationships and SLA metrics (RPS, latency, error rate, CPU, memory)
- **System Analysis** — Performance metrics: accuracy trends, failure analysis, confidence gaps, retrieval tool effectiveness, weight optimization

**Features:** Dark-mode design, real-time analysis, feedback-driven learning, searchable investigation history.

## Tuning & Optimization

### Detection Sensitivity

Z-score threshold (default 3.0 → ~0.3% of normal distribution):
- Increase to 4.0 for fewer false positives (miss subtle anomalies)
- Decrease to 2.5 for higher recall (more false positives)

IsolationForest contamination (default 0.05):
- Higher (0.1) catches more correlated anomalies, more false positives
- Lower (0.02) stricter, fewer false positives

### Investigation Cost

| Lever | Impact | Trade-off |
|-------|--------|-----------|
| max_steps: 15 → 10 | -20s latency | Less thorough investigation |
| top_k: 15 → 10 logs | -30% Pinecone latency | Fewer candidates |
| Redis enabled | -5-10s tool caching | Requires Redis |
| Model: Sonnet → Haiku | -50% cost | Worse reasoning |

### Adding Tools

LangChain `@tool` in `agent/tools.py`:
```python
@tool
def my_tool(service: str, query: str) -> str:
    """Tool description for LLM"""
    return json.dumps(result)
```
Tools must return JSON; LLM reads descriptions to decide when to call.

### Monitoring

**PostgreSQL investigation history:**
```sql
SELECT incident_id, incident_type, created_at, final_root_cause, final_confidence
FROM investigations
WHERE created_at > NOW() - INTERVAL '7 days'
ORDER BY created_at DESC;

SELECT verdict, COUNT(*) FROM feedback
GROUP BY verdict;
```

**Retrieval weight evolution:**
```sql
SELECT source, incident_type, weight, updated_at
FROM retrieval_weights
WHERE incident_type = 'database'
ORDER BY updated_at DESC;
```

**Accuracy by incident type:**
```python
from feedback.stats import compute_accuracy_trend

trend = compute_accuracy_trend(store)
for day in trend[-7:]:  # Last 7 days
    print(f"{day['date']}: {day['accuracy']:.0%} ({day['sample_size']} investigations)")
```

## Troubleshooting

### Common Issues

| Issue | Diagnosis | Fix |
|-------|-----------|-----|
| Pinecone: "$gte operator must be followed by a number" | ISO timestamps need conversion | Already handled by `resolve_timestamp()` helper |
| PostgreSQL: "password authentication failed" | Wrong credentials in .env | Check FEEDBACK_URI and TIMESCALE_URI format |
| Anomalies not detected | Z-score threshold too strict | Lower threshold: `detect(metrics, z_threshold=2.5)` |
| Weights not applied | Incident_type missing | Verify `incident['anomaly_type']` set; check retrieval_weights table |
| Investigation timeout (>120s) | Pinecone latency or too many steps | Reduce `max_steps` to 10, check Pinecone status |
| Memory bloat | Large incident bundles | Implement log compression (see `processing/`) |

## Performance & Limits

| Metric | Value | Notes |
|--------|-------|-------|
| Detection latency | 100-200ms | Batch processing, PELT is bottleneck |
| Investigation latency | 30-90s | Pinecone reranking dominant cost |
| Token usage | 30-50k / investigation | Varies by incident complexity |
| Cost | $0.10-0.15 / investigation | At current Claude pricing |
| Max steps | 15 | Prevent runaway agents |
| Throughput | ~1M metrics/min | Single machine |

**Cost Reduction:**
- Reduce `max_steps` 15 → 10: -20s, -15% tokens
- Use Haiku for plan/verify: -50% cost, -5% quality
- Enable Redis: -10s for common incident types

## Limitations & Future Work

| Component | Current | Future |
|-----------|---------|--------|
| Detection | Heuristic incident type classification | ML classifier trained on feedback verdicts |
| Investigation | Max 15 steps (prevents runaway agents) | Adaptive step count based on incident type |
| Retrieval | (source, incident_type) weights | (source, incident_type, service) weights for finer tuning |
| Scaling | Single machine, ~1M metrics/min | Distributed detection + retrieval for 1000s/day |
| Learning | Manual engineer feedback loop | Auto-validation against ticket systems (Jira, PagerDuty) |

## Contributing

**Code style:** Type hints required, no comments unless "why" is non-obvious, test with real incident data.

**Adding features:**
1. Choose layer (detection, investigation, retrieval, feedback)
2. Maintain type contracts (see data models above)
3. Test with `tests/data/incidents/` bundles
4. Update relevant docs

## Documentation

| Document | Purpose |
|----------|---------|
| [SETUP.md](docs/SETUP.md) | Backend setup, Docker/Kubernetes deployment |
| [API_REFERENCE.md](docs/API_REFERENCE.md) | Function signatures, examples, workflows, troubleshooting |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, algorithms, data models, performance analysis |

Example incidents in `data/incidents/` for testing.
# SIREN Architecture Deep Dive

## System Overview

SIREN is a three-layer incident investigation system with continuous self-improvement. Data flows from detection through investigation to feedback, creating a closed loop where engineer verdicts improve future investigations.

```
Raw Metrics (CSV or time-series)
    ↓
┌─────────────────────────────────────────────────────────────┐
│ DETECTION LAYER (detection/)                                │
│ Statistical (z-score, PELT) + ML (IsolationForest)         │
│ → Incident classification + deduplication                   │
│ Output: anomalies[], incident{type, severity, services}    │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ INVESTIGATION LAYER (agent/, retrieval/)                    │
│ LangGraph 4-node agent with multi-modal retrieval tools     │
│ Logs (Pinecone) + Metrics (TimescaleDB) + Graph (Neo4j)    │
│ → Root cause hypothesis with evidence ledger                │
│ Output: final_root_cause, final_confidence, final_report    │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ FEEDBACK LAYER (feedback/)                                  │
│ Engineer provides verdict (correct/partial/wrong)           │
│ → Retrieval weight optimization by (source, incident_type)  │
│ Output: updated weights persisted to PostgreSQL             │
└─────────────────────────────────────────────────────────────┘
    ↓
[Weights applied to next investigation] (closed loop)

## Layer 1: Anomaly Detection

Runs in <200ms on typical incident bundles. Multi-method ensemble (statistical + ML) reduces false positives while catching both abrupt and gradual anomalies.

### Pipeline

**Input:** List[Dict] with keys: timestamp, service, error_rate, latency_p99, latency_p50, rps, cpu, memory

**Process:**
1. Split metrics into baseline (first 30% of rows) and incident window (remainder)
2. Run statistical detector (z-score + PELT) on each service/metric
3. Run ML detector (IsolationForest) on each service across all metrics
4. Merge anomaly lists, deduplicate within 5-min windows
5. Classify incident type from anomaly patterns (heuristics)
6. Assign severity (critical/high/medium based on z-score)

**Output:** `(anomalies, incident)` tuple where:
- `anomalies`: List[Dict] with timestamp, service, metric, value, zscore, baseline_mean, baseline_std, detector, changepoint
- `incident`: Dict with incident_id, timestamp, affected_services, anomaly_type, severity, triggering_metrics

### Statistical Detector (`detection/statistical.py`)

Per-service, per-metric z-score detection with changepoint awareness.

**Algorithm:**
1. Baseline: first 30% of rows per service → compute mean and std
2. For each metric in incident rows: z = (value - mean) / std
3. Flag if |z| > threshold (default 3.0)
4. PELT changepoint detection (ruptures library, pen=3) finds abrupt level shifts

**Why this approach:**
- Threshold is configurable (3.0σ captures ~0.3% of normal distribution)
- PELT efficiently finds change-points without manual window selection
- Per-service prevents one anomalous service from skewing others' baselines
- Changepoint flag helps distinguish between gradual and abrupt anomalies

**Limitations:**
- Assumes normal distribution in baseline (may underdetect in skewed metrics)
- Fixed 30% baseline cutoff works for most incident bundles but not all data distributions

### ML Detector (`detection/ml_detector.py`)

IsolationForest for multivariate anomaly detection. Catches correlated metric shifts that z-score alone misses.

**Algorithm:**
1. Baseline rows: Extract feature matrix [error_rate, latency_p99, latency_p50, rps, cpu, memory]
2. Train IsolationForest(contamination=0.05, random_state=42) on baseline
3. Score incident rows with trained model
4. Flag rows where anomaly_score < threshold

**Why Isolation Forest:**
- No distance metric needed (works with mixed scales)
- O(n) complexity (fast)
- Detects both point and collective anomalies
- Robust to high-dimensional data

**Limitations:**
- Threshold selection is fixed; would benefit from calibration per incident type
- Currently outputs zscore=-99.0 sentinel (not a real z-score) to fit output contract

### Incident Classification (`detection/trigger.py`)

Heuristic rules map anomaly patterns to typed incidents.

**Classification Logic:**
```python
if memory_max > 85%:
    incident_type = "memory"
elif latency_spike AND NOT error_spike:
    incident_type = "timeout"
elif error_spike AND latency_spike:
    incident_type = "compute"
elif latency_spike AND rps_spike:
    incident_type = "network"
elif error_spike:
    incident_type = "database"
else:
    incident_type = "compute"  # fallback
```

**Severity Scoring:**
- critical: z > 5.0 (0.00006% of distribution)
- high: z > 3.0 (0.3%)
- medium: z ≥ 0

**Future Enhancement:** Train ML classifier on engineer feedback verdicts to replace heuristics.

## Layer 2: Investigation Engine

LangGraph agentic system with 4 nodes: Plan → Investigate → Verify → Report. Completes in 30-90s by combining multi-modal retrieval with LLM reasoning.

### Graph Structure

**Nodes (in execution order):**
1. **Planner** — Reads anomalies + origin_service, generates step-by-step investigation plan + initial hypothesis
2. **Investigator** — Loop node (max 15 iterations) that calls tools, evaluates evidence, updates hypotheses
3. **Verifier** — Challenges the final hypothesis, adjusts confidence score, ensures reasoning is sound
4. **Reporter** — Generates markdown RCA report with citations to evidence

**State Flow:**
```
InvestigationState {incident_id, anomalies, origin_service, incident_type, window_start/end}
    ↓
Planner → investigation_plan[], initial_hypothesis
    ↓
Investigator (loop) → tool_history[], evidence_ledger{}, hypotheses[]
    ↓
Verifier → final_root_cause, final_confidence (0.0-1.0)
    ↓
Reporter → final_report (markdown)
    ↓
Output state with all fields populated
```

**Implementation:** `agent/graph.py` (graph definition), `agent/nodes.py` (node logic)

### Investigation State

Defined in `agent/state.py` as InvestigationState TypedDict. Flows through all 4 nodes.

**Input fields:**
- `incident_id`: str — unique identifier
- `anomalies`: list[dict] — from detection layer
- `origin_service`: str — primary affected service
- `window_start`, `window_end`: str — ISO timestamps (5 min before/after anomalies)
- `incident_type`: str — classified type (compute, network, database, memory, timeout)

**Working memory (evolving):**
- `investigation_plan`: list[str] — steps generated by planner
- `current_step`: int — which step the investigator is on
- `hypotheses`: list[dict] — evolving hypotheses with confidence deltas
- `tool_history`: list[dict] — tool calls made, arguments, results
- `evidence_ledger`: dict — keyed evidence items (ev_001, ev_002, ...)

**Output fields:**
- `final_root_cause`: str — conclusion (service, component, pattern)
- `final_confidence`: float — 0.0-1.0, adjusted by verifier
- `final_report`: str — markdown RCA with evidence citations

### Retrieval Tools

Tools defined in `agent/tools.py` as LangChain `@tool` decorated functions. Agent decides which to call based on state and tool descriptions.

**Tool: query_logs**
```python
def query_logs(service: str, query: str, 
               window_start: str, window_end: str, top_k: int = 10) → str
```
- Resolves ISO timestamps to Unix seconds (Pinecone requirement) via `resolve_timestamp()`
- Vector searches Pinecone logs index with query embedding
- Reranks with Cohere (if available)
- Applies learned weights: score *= retrieval_weights[(source="query_logs", incident_type)]
- Returns JSON list of matching logs with metadata

**Tool: get_metrics**
```python
def get_metrics(service: str, window_start: str, window_end: str) → str
```
- Queries TimescaleDB for baseline metrics (pre-incident window)
- Queries TimescaleDB for peak metrics (during incident)
- Computes ratios and anomaly severity
- Returns JSON dict with baseline, peak, deltas

**Tool: get_dependencies**
```python
def get_dependencies(service: str) → str
```
- Queries Neo4j dependency graph
- Returns adjacent services (upstream/downstream)
- Used to prioritize which services to investigate

**Tool: search_runbook**
```python
def search_runbook(query: str, top_k: int = 5) → str
```
- Embeds query, searches docs/ runbooks via Pinecone
- Returns relevant documentation for remediation

**Tool Caching:**
Results cached in Redis for 300s (configurable via TOOL_CACHE_TTL env var)

### Hypothesis Evolution

Each tool call generates evidence that updates hypothesis confidence.

**Hypothesis object:**
```python
{
    "id": "hyp_001",
    "statement": "database connection pool exhaustion",
    "confidence": 0.85,           # 0.0 to 1.0
    "evidence_for": ["ev_001", "ev_003"],
    "evidence_against": [],
    "status": "open" | "closed"
}
```

**After each tool call:**
1. Tool result added to evidence_ledger with unique ID
2. Fast LLM (Haiku) reads hypothesis + new evidence
3. Judges: does this support, contradict, or not affect the hypothesis?
4. Confidence delta (-0.3 to +0.3) applied
5. Hypothesis status may change to "closed" if conclusion reached

**Example flow:**
```
Initial: "API gateway is bottlenecked" (confidence 0.4)
Tool 1: query_logs(api-gateway) → no errors found
  → Confidence -= 0.2 → now 0.2 (evidence_against)
Tool 2: get_metrics(database) → 10x error spike during incident
  → Shift to new hypothesis: "Database error cascade" (confidence 0.8)
Tool 3: get_dependencies(database) → API calls database
  → Supports "Database error cascade" → confidence += 0.15 → 0.95
```

## Layer 3: Feedback & Learning

Closed-loop system where engineer verdicts improve future investigations via retrieval weight optimization.

### Data Flow

**Investigation completes** → saved to PostgreSQL investigations table with:
- incident_id, incident_type, tool_history[], evidence_ledger{}, final_root_cause, final_confidence

**Engineer reviews RCA** (dashboard History page or programmatic API) → provides verdict:
- ✓ **Correct** — investigation result matches real root cause
- ⚠ **Partial** — correct root cause but missing important context
- ✗ **Wrong** — investigation missed the real cause (optionally provide correction)

**Feedback persisted** to PostgreSQL feedback table with verdict + engineer_notes

**Weight recomputation** (triggered via dashboard or API):
- Loads all investigations with feedback verdicts
- For each (source, incident_type) pair:
  - Counts: investigations where this tool appeared AND verdict was "correct"
  - Computes: success_rate = (correct+1) / (total+2) [Laplace smoothing]
  - Applies: weight = 0.5 + success_rate (range [0.5, 1.5])
- Persists weights to retrieval_weights table
- Next investigation applies weights to boost scores from high-performing tools

**Result:** Positive feedback loop where correct investigations reinforce effective tools

### Weight Computation

Formula in `feedback/optimizer.py:recompute_weights()`:

```python
success_rate = (correct_count + 1) / (total_count + 2)  # Laplace smoothing
weight = 0.5 + success_rate
# Range: [0.5, 1.5]

# Example:
# (source="query_logs", incident_type="database")
# - Tool appeared in 6 database investigations
# - 5 of those verdicts were "correct"
# - success_rate = (5+1)/(6+2) = 0.75
# - weight = 0.5 + 0.75 = 1.25x
```

**Why Laplace Smoothing (adding 1/2)?**
- Stabilizes for small sample sizes (don't overfit to lucky early successes)
- Prevents zero weights (source appears in 0 correct out of 1 total)
- Prevents infinity weights

**Why [0.5, 1.5] range?**
- Floor 0.5x: Penalize poor tools, don't eliminate them completely
- Ceiling 1.5x: Cap benefit of very good tools
- Prevents any single tool from dominating retrieval

**Application:** During investigation, scores boosted by weight factor:
```
retrieval_score *= retrieval_weights[(source, incident_type)]
```

### Analytics (`feedback/stats.py`)

**Accuracy Trend**
```python
compute_accuracy_trend(store) → list[{date, accuracy, sample_size}]
```
Daily breakdown of correct/total verdicts

**Confidence Calibration**
```python
compute_confidence_calibration(store) → list[{confidence_bin, actual_accuracy, sample_size}]
```
Buckets investigations into confidence deciles, shows if predicted confidence matches actual accuracy. Perfect calibration is y=x line.

**Source Effectiveness**
```python
compute_source_effectiveness(store) → list[{source, usage_count, success_rate}]
```
For each tool, how many investigations used it and what fraction were correct

## Data Persistence

All data persists to PostgreSQL via `feedback/store.py`. Schema defined in `docs/SETUP.md`.

### investigations table

```sql
incident_id TEXT PRIMARY KEY
incident_type TEXT NOT NULL  -- From detection layer
final_root_cause TEXT
final_confidence FLOAT
final_report TEXT  -- Markdown RCA
tool_history JSONB  -- Array of tool calls
evidence_ledger JSONB  -- Key-value evidence items
created_at TIMESTAMP DEFAULT NOW()
```

**Row example:**
```json
{
  "incident_id": "compute_20260421T062715",
  "incident_type": "compute",
  "final_root_cause": "database_connection_pool_exhaustion",
  "final_confidence": 0.87,
  "tool_history": [
    {"step": 1, "tool_name": "query_logs", "result_summary": "Found 12 timeout errors"},
    {"step": 2, "tool_name": "get_metrics", "result_summary": "Database CPU 98%, connections 495/500"},
    ...
  ],
  "evidence_ledger": {
    "ev_001": {"tool": "query_logs", "summary": "Logs show connection timeout errors"},
    "ev_002": {"tool": "get_metrics", "summary": "Database CPU spike correlates with error spike"}
  }
}
```

### feedback table

```sql
incident_id TEXT NOT NULL REFERENCES investigations(incident_id)
verdict TEXT CHECK (verdict IN ('correct', 'partial', 'wrong'))
correct_root_cause TEXT  -- Null if verdict='correct'
engineer_notes TEXT
created_at TIMESTAMP DEFAULT NOW()
```

**Row example:**
```json
{
  "incident_id": "compute_20260421T062715",
  "verdict": "correct",
  "engineer_notes": "Excellent diagnosis, identified pool exhaustion correctly"
}
```

### retrieval_weights table

```sql
source TEXT NOT NULL  -- Tool name (query_logs, get_metrics, etc)
incident_type TEXT NOT NULL  -- Incident type (compute, database, etc)
weight FLOAT DEFAULT 1.0  -- Range [0.5, 1.5]
updated_at TIMESTAMP DEFAULT NOW()
PRIMARY KEY (source, incident_type)
```

**Row example:**
```json
{
  "source": "query_logs",
  "incident_type": "database",
  "weight": 1.38,
  "updated_at": "2026-04-21T06:30:00Z"
}
```

## Integration Points

**Currently Implemented:**
- CSV metrics ingestion via `python investigate.py <metrics.csv>` (programmatic API in `investigate.run_investigation()`)
- Streamlit dashboard (`dashboard/app.py`) for feedback collection and analysis
- PostgreSQL for persistent storage

**Possible Future Integrations:**
- Prometheus scrape endpoint (pull metrics continuously)
- Datadog webhook (push incidents to SIREN)
- Slack notifications (alert user when investigation completes)
- PagerDuty (auto-create incident with RCA)
- Custom incident sources (honeycomb, NewRelic, etc)

## Performance

Measured on typical incident bundles (10-50 anomalies, 1000-5000 log lines, 500-2000 metric rows).

### Detection Layer
- **Latency:** 100-200ms (single pass + PELT changepoint)
- **Memory:** ~10MB per 10k metrics
- **Throughput:** 1M+ metrics/minute (CPU-bound)

### Investigation Layer
- **Latency:** 30-90s per investigation
  - Planner: 2-3s
  - Investigator loop: 20-60s (typically 5-7 tool calls)
  - Verifier: 3-5s
  - Reporter: 2-3s
- **Token usage:** 30-50k tokens per investigation (varies with incident complexity)
- **Cost:** ~$0.10-0.15 per investigation at current Claude pricing
- **Bottleneck:** Pinecone + Cohere reranking latency (3-5s per query_logs call)

### Feedback Layer
- **Weight recomputation:** 1-2s (SQL aggregation + Python calculation)
- **Storage:** ~1KB per investigation record, 100KB per feedback record

### Optimization Levers
1. **Reduce max_steps:** (default 15) → 10 saves ~20s
2. **Lower top_k:** (default 15 logs, 10 traces, 5 docs) → half saves ~30% latency
3. **Enable Redis:** Saves 5-10s for repeated tool queries
4. **Faster model:** Use Haiku for planner, Sonnet for investigator (current setup)

## Error Handling

System implements graceful degradation: failures don't halt investigation, just reduce confidence.

**Pinecone (logs/docs) unavailable:**
- query_logs tool returns empty
- Investigation continues with metrics + dependencies
- Final confidence reduced (no log evidence available)
- Tool still counted in tool_history (helps debugging)

**TimescaleDB (metrics) unavailable:**
- get_metrics returns cached or zeroed metrics
- Investigation continues with logs + dependencies
- Final confidence reduced (no baseline comparison)

**Neo4j (dependencies) unavailable:**
- get_dependencies returns empty list
- Investigation continues with logs + metrics
- Less likely to identify cascading failures

**Tool timeout (>30s):**
- LLM stops waiting and moves to next step
- Evidence_ledger marked with "timeout" for that tool
- Confidence penalized proportional to evidence missing

**Redis unavailable:**
- Tool caching disabled (each call hits backend)
- Investigation still works, just slower
- No functional impact, only performance

**PostgreSQL (feedback store) unavailable:**
- Investigation completes normally
- save_investigation() fails silently (logged as warning)
- Feedback loop broken for that cycle; weights don't update
- Can be retried when database recovers

### Checkpointing (Optional)

LangGraph can checkpoint state to PostgreSQL after each node. Configured via CHECKPOINT_URI env var. If empty, state stays in-memory (no resume capability on crash, but faster).

## Testing

Located in `tests/` directory.

**Unit Tests:**
- Detection algorithms against synthetic metrics with known anomalies
- Weight computation formula (Laplace smoothing edge cases)
- Timestamp resolution (ISO to Unix conversion)
- Incident type classification heuristics

**Integration Tests:**
- Full pipeline with real incident bundles (data/incidents/)
- Tool chaining (plan → investigate → verify → report)
- Feedback verdicts trigger weight recomputation
- Weights applied in next investigation

**Benchmark Tests:**
- Real incident bundles with known root causes
- Accuracy by incident type
- Confidence calibration (predicted vs actual)
- Latency and token usage profiling

**Run tests:**
```bash
pytest tests/ -v
pytest tests/test_detection.py::test_z_score -v
pytest tests/test_integration.py::test_full_pipeline -v
```

## Security Considerations

**API Keys:**
- All keys stored in .env (never committed, in .gitignore)
- Never logged or included in error messages
- Rotate keys if .env accidentally committed

**Data Sensitivity:**
- Logs and metrics can contain PII (email addresses, user IDs)
- Restrict PostgreSQL access to authorized personnel
- Consider log scrubbing before indexing to Pinecone

**Feedback Data:**
- Engineer verdicts could reveal expertise levels or incident frequency
- Restrict dashboard access if incident patterns are sensitive

**LLM Prompts:**
- Anomaly descriptions and logs sent to Claude API
- Anthropic API has data retention policy (check terms)
- Consider on-prem LLM alternative for highly sensitive data

**Principle:** Minimize data exposure; only send incident details when investigation is necessary.

# SIREN Setup & Deployment Guide

## Local Development Setup

### Prerequisites

- Python 3.13+
- PostgreSQL 14+
- Neo4j 5.x
- Redis 6.x (optional, for caching)
- Docker (recommended for databases)

### Step 1: Clone and Install

```bash
git clone <repository>
cd siren

# Create virtual environment
python3.13 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Database Setup

#### PostgreSQL (Feedback Store)

```bash
# Start PostgreSQL
docker run -d \
  --name siren-postgres \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=siren_feedback \
  -p 5432:5432 \
  postgres:16

# Create schema
psql postgresql://postgres:password@localhost/siren_feedback < docs/schema.sql

# Or manually:
psql -U postgres -d siren_feedback
```

**Schema:**
```sql
CREATE TABLE investigations (
  incident_id TEXT PRIMARY KEY,
  incident_type TEXT NOT NULL,
  reported_root_cause TEXT,
  reported_confidence FLOAT,
  steps_taken INT,
  final_report TEXT,
  tool_history JSONB,
  evidence_ledger JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE feedback (
  incident_id TEXT NOT NULL REFERENCES investigations(incident_id),
  verdict TEXT CHECK (verdict IN ('correct', 'partial', 'wrong')),
  correct_root_cause TEXT,
  engineer_notes TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE retrieval_weights (
  source TEXT NOT NULL,
  incident_type TEXT NOT NULL,
  weight FLOAT DEFAULT 1.0,
  updated_at TIMESTAMP DEFAULT NOW(),
  PRIMARY KEY (source, incident_type)
);

CREATE INDEX idx_investigations_created_at ON investigations(created_at DESC);
CREATE INDEX idx_feedback_incident ON feedback(incident_id);
```

#### Neo4j (Dependency Graph)

```bash
# Start Neo4j
docker run -d \
  --name siren-neo4j \
  -e NEO4J_AUTH=neo4j/password \
  -p 7687:7687 \
  -p 7474:7474 \
  neo4j:5

# Access web UI: http://localhost:7474
# Default credentials: neo4j / password
```

**Seed Data:**
```cypher
// Create service nodes
CREATE (api:Service {name: "api-gateway"})
CREATE (auth:Service {name: "auth-service"})
CREATE (payment:Service {name: "payment-service"})
CREATE (rec:Service {name: "recommendation-service"})
CREATE (db:Service {name: "database"})
CREATE (cache:Service {name: "cache"})
CREATE (mq:Service {name: "message-queue"})

// Create dependency edges
CREATE (api)-[:CALLS]->(auth)
CREATE (api)-[:CALLS]->(payment)
CREATE (api)-[:CALLS]->(rec)
CREATE (auth)-[:CALLS]->(db)
CREATE (auth)-[:CALLS]->(cache)
CREATE (payment)-[:CALLS]->(db)
CREATE (payment)-[:CALLS]->(mq)
CREATE (rec)-[:CALLS]->(cache)
CREATE (rec)-[:CALLS]->(db)
```

#### TimescaleDB (Metrics)

```bash
# Start TimescaleDB (PostgreSQL with extensions)
docker run -d \
  --name siren-timescale \
  -e POSTGRES_PASSWORD=password \
  -p 5433:5432 \
  timescale/timescaledb:latest-pg15

# Create schema
psql postgresql://postgres:password@localhost:5433/postgres
```

**Schema:**
```sql
CREATE DATABASE siren;
\c siren

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE metrics (
  timestamp TIMESTAMPTZ NOT NULL,
  service TEXT NOT NULL,
  rps DOUBLE PRECISION,
  error_rate DOUBLE PRECISION,
  latency_p50 DOUBLE PRECISION,
  latency_p99 DOUBLE PRECISION,
  cpu DOUBLE PRECISION,
  memory DOUBLE PRECISION
);

SELECT create_hypertable('metrics', 'timestamp', if_not_exists => TRUE);

CREATE INDEX idx_metrics_service_time ON metrics (service, timestamp DESC);
```

#### Redis (Caching)

```bash
# Start Redis
docker run -d \
  --name siren-redis \
  -p 6379:6379 \
  redis:7

# Optional: Test connection
redis-cli ping  # Should return PONG
```

### Step 3: API Keys & Configuration

Create `.env`:

```bash
cp .env.example .env
```

**Edit `.env`:**

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Embeddings & Reranking
OPENAI_API_KEY=sk-...
COHERE_API_KEY=...

# Vector Search
PINECONE_API_KEY=pcsk_...
PINECONE_INDEX=siren-logs

# Databases
NEO4J_URI=bolt://localhost:7687
NEO4J_AUTH=neo4j:password
TIMESCALE_URI=postgresql://postgres:password@localhost:5433/siren
FEEDBACK_URI=postgresql://postgres:password@localhost:5432/siren_feedback

# Caching (optional)
REDIS_URL=redis://localhost:6379

# Settings
TOOL_CACHE_TTL=300
CHECKPOINT_URI=  # Leave empty to disable LangGraph checkpointing
```

### Step 4: Verify Setup

```bash
# Test imports
python -c "from detection import detect; from agent.run import run_investigation; print('✓ All imports OK')"

# Test databases
python << 'EOF'
from feedback.store import FeedbackStore
store = FeedbackStore()
print("✓ PostgreSQL connected")

from retrieval.orchestrator import SirenQueryEngine
engine = SirenQueryEngine()
print("✓ Pinecone connected")
print("✓ All backends ready")
EOF
```

## Running Investigations

### Option 1: CLI

```bash
# Single investigation
python investigate.py data/incidents/cascading_timeout/metrics.csv

# With reindexing
python investigate.py data/incidents/cascading_timeout/metrics.csv --reindex
```

### Option 2: Streamlit Dashboard

```bash
streamlit run dashboard/app.py
```

Visit http://localhost:8501

### Option 3: Programmatic

```python
from investigation import run_investigation

result = run_investigation("data/incidents/database_lock/metrics.csv")
print(result['final_report'])
```

## Production Deployment

### Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: prod_password
      POSTGRES_DB: siren_feedback
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  timescale:
    image: timescale/timescaledb:latest-pg15
    environment:
      POSTGRES_PASSWORD: prod_password
    volumes:
      - timescale_data:/var/lib/postgresql/data
    ports:
      - "5433:5432"

  neo4j:
    image: neo4j:5
    environment:
      NEO4J_AUTH: neo4j/prod_password
    volumes:
      - neo4j_data:/data
    ports:
      - "7687:7687"
      - "7474:7474"

  redis:
    image: redis:7
    ports:
      - "6379:6379"

  siren:
    build: .
    depends_on:
      - postgres
      - timescale
      - neo4j
      - redis
    environment:
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      COHERE_API_KEY: ${COHERE_API_KEY}
      PINECONE_API_KEY: ${PINECONE_API_KEY}
      FEEDBACK_URI: postgresql://postgres:prod_password@postgres:5432/siren_feedback
      TIMESCALE_URI: postgresql://postgres:prod_password@timescale:5432/postgres
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_AUTH: neo4j:prod_password
      REDIS_URL: redis://redis:6379
    ports:
      - "8501:8501"  # Streamlit
    command: streamlit run dashboard/app.py

volumes:
  postgres_data:
  timescale_data:
  neo4j_data:
```

**Start:**
```bash
docker-compose up -d
```

### Kubernetes

Example `siren-deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: siren
spec:
  replicas: 2
  selector:
    matchLabels:
      app: siren
  template:
    metadata:
      labels:
        app: siren
    spec:
      containers:
      - name: siren
        image: siren:latest
        ports:
        - containerPort: 8501
        env:
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: siren-secrets
              key: anthropic-key
        - name: FEEDBACK_URI
          value: postgresql://siren-postgres:5432/siren_feedback
        - name: TIMESCALE_URI
          value: postgresql://siren-timescale:5432/siren
        - name: NEO4J_URI
          value: bolt://siren-neo4j:7687
        - name: REDIS_URL
          value: redis://siren-redis:6379
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
---
apiVersion: v1
kind: Service
metadata:
  name: siren
spec:
  selector:
    app: siren
  ports:
  - port: 8501
    targetPort: 8501
  type: LoadBalancer
```

**Deploy:**
```bash
kubectl apply -f siren-deployment.yaml
```

## Monitoring

### Health Checks

```python
# health_check.py
from feedback.store import FeedbackStore
from retrieval.orchestrator import SirenQueryEngine

def check_health():
    try:
        store = FeedbackStore()
        store.conn.rollback()
        engine = SirenQueryEngine()
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

if __name__ == "__main__":
    print(check_health())
```

### Logs

**Streamlit logs:**
```bash
tail -f ~/.streamlit/logs/
```

**Application logs:**
```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('siren.log'),
        logging.StreamHandler()
    ]
)
```

### Metrics Export

```python
# Prometheus metrics
from prometheus_client import Counter, Histogram, start_http_server

investigations_total = Counter('siren_investigations_total', 'Total investigations')
investigation_duration = Histogram('siren_investigation_seconds', 'Investigation duration')
feedback_verdicts = Counter('siren_feedback_verdicts_total', 'Feedback verdicts', ['verdict'])

# Expose metrics on :8000/metrics
start_http_server(8000)
```

## Upgrades

### Schema Migrations

```bash
# Backup
pg_dump postgresql://user:pass@localhost/siren_feedback > backup.sql

# Apply migration
psql postgresql://user:pass@localhost/siren_feedback < migrations/001_add_column.sql
```

### Dependency Updates

```bash
# Check for updates
pip list --outdated

# Update with tests
pip install --upgrade -r requirements.txt
pytest tests/
```

## Troubleshooting

### Port Already in Use

```bash
# Find and kill process on port 5432
lsof -i :5432
kill -9 <PID>

# Or use different port
docker run -p 5433:5432 postgres:16
# Update .env: FEEDBACK_URI=postgresql://user:pass@localhost:5433/...
```

### Out of Memory

```bash
# Increase Docker memory
docker update --memory 4g siren-postgres

# Or Docker Desktop → Settings → Resources → Memory
```

### Slow Investigations

```bash
# Check Pinecone status
curl -i https://api.pinecone.io/status

# Check database query performance
EXPLAIN ANALYZE SELECT * FROM investigations WHERE created_at > NOW() - INTERVAL '1 day';
```

### API Rate Limits

```bash
# Wait for quota reset
# Or upgrade Anthropic plan: console.anthropic.com

# Reduce token usage
# - Lower max_steps (default 15 → 10)
# - Lower top_k in retrieval (15 → 10)
# - Use faster model for some nodes
```

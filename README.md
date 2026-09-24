# PlanGuard

**PostgreSQL Workload Analyzer & Index Experimentation Platform**

> Evidence over assertion. PostgreSQL is the authority on PostgreSQL.

---

## Quick Start

### Prerequisites
- Docker + Docker Compose
- Node.js 20+
- Python 3.12+

### 1. Copy environment file
```bash
cp .env.example .env
# Edit .env and fill in APP_ENCRYPTION_KEY (see comment for generation command)
```

### 2. Start infrastructure
```bash
docker compose up app-postgres redis fixture-postgres -d
```

### 3. Run database migrations
```bash
cd apps/api
DATABASE_URL=postgresql+psycopg://planguard:planguard@localhost:5432/planguard \
  python3 -m alembic upgrade head
```

### 4. Start the API
```bash
cd apps/api
uvicorn app.main:app --reload --port 8000
```

### 5. Start the frontend
```bash
cd apps/web
npm run dev
# → http://localhost:5173
```

### 6. (Optional) Start the RQ worker
```bash
cd apps/api
rq worker --with-scheduler planguard-default
```

---

## Architecture

```
apps/
  api/                        FastAPI backend
    app/
      analysis/
        plan_parser.py        EXPLAIN JSON → PlanNode tree
        candidate_generator.py  Deterministic rule-based index candidates
        experiment_runner.py  HypoPG-powered hypothetical plan comparison
        scorer.py             Evidence-based scoring (no LLM required)
      api/
        workspaces.py         REST endpoints + capability detection
      domains/                SQLAlchemy ORM models
      workers/tasks.py        RQ background jobs
  web/                        React + TypeScript + Tailwind v4
    src/
      api/client.ts           Typed API client
      features/               Page-level feature components
      app/AppShell.tsx        Navigation shell
      lib/utils.ts            Formatting utilities
infra/
  docker/                     Dockerfiles
  postgres/fixtures/          Target DB seed SQL
docker-compose.yml
```

## Core Workflow

1. **Connect** → provide PostgreSQL credentials → capability check
2. **Capture** → reads `pg_stat_statements` → upserts `QueryFingerprint`
3. **Analyze** → `EXPLAIN (FORMAT JSON)` → extracts signals → generates `IndexCandidate`
4. **Experiment** → `hypopg_create_index` + re-EXPLAIN → computes `plan_diff`
5. **Score** → deterministic scoring: benefit − storage − write − overlap
6. **Recommend** → `RECOMMENDED | REVIEW_REQUIRED | INCONCLUSIVE | REJECTED`
7. **Migrate** → `CREATE INDEX CONCURRENTLY` SQL generated for review

## Key Design Decisions

| Decision | Rationale |
|---|---|
| HypoPG for experiments | True PostgreSQL planner cost, not heuristic estimation |
| Deterministic scoring | Reproducible, auditable — no LLM drift |
| SAVEPOINT protection | HypoPG index always rolled back, never persists |
| Read-only target connection | Zero risk to production data |
| RQ over Celery | Simpler, Redis-native, sufficient for workload |
| `CONCURRENTLY` in migration output | Reminds user to run non-blocking in production |

## API Reference

```
GET  /api/v1/workspaces                          List workspaces
POST /api/v1/workspaces                          Create workspace
GET  /api/v1/workspaces/{id}                     Get workspace
POST /api/v1/workspaces/{id}/connection/test     Test connection
POST /api/v1/workspaces/{id}/connection          Save connection
POST /api/v1/workspaces/{id}/snapshots           Trigger capture
GET  /api/v1/workspaces/{id}/queries             List fingerprints
GET  /api/v1/workspaces/{id}/queries/{qid}       Get query + plan
POST /api/v1/workspaces/{id}/queries/{qid}/analyze  Re-analyze
GET  /api/v1/workspaces/{id}/recommendations     List recommendations
GET  /api/v1/recommendations/{id}                Get recommendation
POST /api/v1/recommendations/{id}/migration      Generate SQL
GET  /api/docs                                   Swagger UI
```

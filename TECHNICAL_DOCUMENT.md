# PlanGuard — Technical Architecture & Engine Specification

**PlanGuard** is an automated PostgreSQL workload analyzer and index optimizer. It ingests production query telemetry from `pg_stat_statements`, extracts query plan bottlenecks via native `EXPLAIN`, synthesizes candidate indexes using deterministic relational heuristics, simulates candidate performance in-memory using PostgreSQL's `hypopg` extension, and outputs safe, production-ready `CREATE INDEX CONCURRENTLY` migration SQL.

---

## 1. System Architecture

PlanGuard runs as a two-tier application interfacing directly with target PostgreSQL instances over standard `libpq` wire protocol (`psycopg3`):

```
┌─────────────────────────────────────────────────────────────┐
│                       Web Frontend                          │
│        React 19 · Vite · TypeScript · TanStack Query        │
│          Tailwind CSS · Lucide Icons · Sonner Toasts        │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / JSON
┌──────────────────────────────▼──────────────────────────────┐
│                    PlanGuard FastAPI API                    │
│   Domain Routers · AsyncSession (SQLAlchemy) · Alembic      │
│  Candidate Generator · Plan Signal Parser · Scoring Engine  │
└──────┬───────────────────────┬──────────────────────────────┘
       │ Background Tasks      │ psycopg3 (Direct libpq)
┌──────▼────────┐       ┌──────▼──────────────────────────────┐
│ PlanGuard DB  │       │          Target Database            │
│  (PostgreSQL) │       │   (Local, AWS RDS, Supabase, etc.)  │
│  Workspaces   │       │  • pg_stat_statements (Telemetry)  │
│  Snapshots    │       │  • EXPLAIN (FORMAT JSON)            │
│  Experiments  │       │  • HypoPG (In-Memory Simulation)    │
│  Migs/History │       │  • pg_stat_user_indexes (Inventory) │
└───────────────┘       └─────────────────────────────────────┘
```

### Key Principle: Zero External API Dependency
PlanGuard requires **no external AI APIs, LLM providers, or cloud agents**. All analysis is 100% deterministic and runs directly against the connected PostgreSQL database using PostgreSQL’s own query planner and cost model.

---

## 2. Core Processing Pipeline

```
  ┌─────────────────────────────────────────────────────────┐
  │ 1. Connection & Capability Probing                      │
  │    Verifies PostgreSQL connectivity, version banner,    │
  │    pg_stat_statements, hypopg, and read-only access.    │
  └────────────────────────────┬────────────────────────────┘
                               │
  ┌────────────────────────────▼────────────────────────────┐
  │ 2. Workload Ingestion                                   │
  │    Reads pg_stat_statements filtered to target dbid.   │
  │    Extracts calls, total_time, mean_time, buffer hits.  │
  │    Computes workload_impact_score per query.            │
  └────────────────────────────┬────────────────────────────┘
                               │
  ┌────────────────────────────▼────────────────────────────┐
  │ 3. Baseline Plan Extraction                             │
  │    Executes EXPLAIN (FORMAT JSON) on target database.   │
  │    Extracts plan signals: Seq Scan, Sort, Hash Join.    │
  └────────────────────────────┬────────────────────────────┘
                               │
  ┌────────────────────────────▼────────────────────────────┐
  │ 4. Heuristic Candidate Synthesis                        │
  │    Applies relational rules (R1–R5) against WHERE,      │
  │    ORDER BY, and JOIN conditions. Detects prefix overlap│
  │    against physical indexes in pg_stat_user_indexes.    │
  └────────────────────────────┬────────────────────────────┘
                               │
  ┌────────────────────────────▼────────────────────────────┐
  │ 5. Isolated HypoPG Simulation                           │
  │    Inside a SAVEPOINT transaction:                      │
  │    • hypopg_create_index(definition)                    │
  │    • EXPLAIN (FORMAT JSON) query                        │
  │    • hypopg_relation_size(index_oid)                    │
  │    • ROLLBACK TO SAVEPOINT + hypopg_reset()             │
  └────────────────────────────┬────────────────────────────┘
                               │
  ┌────────────────────────────▼────────────────────────────┐
  │ 6. Scoring, Recommendation & Artifact Generation        │
  │    Calculates cost reduction ratio, node change,        │
  │    penalizes storage & overlap. Generates deterministic │
  │    CREATE INDEX CONCURRENTLY and rollback DDL.          │
  └─────────────────────────────────────────────────────────┘
```

---

## 3. Pipeline Component Details

### A. Workload Ingestion & Query Normalization
- **Scoping to Active Database:** In PostgreSQL clusters (e.g. Supabase, AWS Aurora), `pg_stat_statements` is cluster-wide. PlanGuard scopes capture to `dbid = (SELECT oid FROM pg_database WHERE datname = current_database())`.
- **System Query Filtering:** Excludes internal PostgreSQL catalogs (`pg_%`, `information_schema`), Supabase platform schemas (`storage.`, `auth.`, `vault.`), and utility statements (`COMMIT`, `SET`, `BEGIN`). Only captures true application DML queries (`SELECT`, `WITH`, `INSERT`, `UPDATE`, `DELETE`).
- **Normalized Query Fingerprinting:** Groups queries by `queryid` and computes each query's impact:
  $$\text{Impact Score} = \frac{\text{Query Total Time}}{\sum \text{Workload Total Time}}$$

### B. Relational Heuristic Candidate Generator
Candidate generation is rule-driven (`candidate_generator.py`), inspecting plan signals:
- **Rule 1 (Seq Scan with Filter):** Indexes columns present in filter predicates (equality columns first, followed by range conditions).
- **Rule 2 (Seq Scan with Order Match):** Indexes sort keys when query contains `ORDER BY`.
- **Rule 3 (Sort Node Elimination):** Indexes sort keys directly to eliminate separate `Sort` nodes from the execution tree.
- **Rule 4 (Hash Join / Nested Loop):** Indexes join key columns on the probe/inner relation.
- **Prefix Overlap Detection:** Cross-references existing indexes in `pg_stat_user_indexes`. If candidate `(status)` is already the leading prefix of `(status, created_at)`, it marks it as `REDUNDANT` to avoid index bloat.

### C. HypoPG Simulation Engine
- Runs entirely in-memory using PostgreSQL's C-extension `hypopg`.
- Generates a hypothetical index via `SELECT * FROM hypopg_create_index('CREATE INDEX ON "table" ("col")')`.
- Re-runs `EXPLAIN (FORMAT JSON)` while the hypothetical index is active in the backend process memory.
- Calculates:
  $$\text{Cost Reduction Ratio} = \frac{\text{Baseline Cost} - \text{Optimized Cost}}{\text{Baseline Cost}}$$
- Immediately issues `ROLLBACK TO SAVEPOINT` and `SELECT hypopg_reset()`. Zero index pages are written to disk, and no write locks are held on application tables.

### D. Scoring & Recommendation Synthesis
Candidates receive a composite score:
$$\text{Score} = \text{Benefit} - \text{Storage Penalty} - \text{Write Penalty} - \text{Overlap Penalty}$$
- **RECOMMENDED:** Cost reduction $\ge 25\%$, plan changed (`Seq Scan` $\rightarrow$ `Index Scan`), high confidence.
- **REVIEW_REQUIRED:** Marginal improvement ($10\% - 25\%$) or elevated storage penalty.
- **REJECTED:** Redundant prefix or negative cost differential.

### E. Migration Artifacts
For every recommendation, PlanGuard generates idempotent DDL:
- **Deploy SQL:**
  ```sql
  CREATE INDEX CONCURRENTLY IF NOT EXISTS "idx_orders_status"
  ON "public"."orders" USING btree ("status");
  ```
- **Rollback SQL:**
  ```sql
  DROP INDEX CONCURRENTLY IF EXISTS "public"."idx_orders_status";
  ```

---

## 4. Verification Benchmarks

### Local E-Commerce Dataset (115,000+ rows)
- **Table:** `orders` (25,000 rows), `order_items` (50,000 rows)
- **Bottleneck Query:** `SELECT id, user_id, total_amount, shipping_city, created_at FROM orders WHERE status = $1 ORDER BY created_at DESC LIMIT $2;`
- **Baseline Plan:** `Seq Scan` on `orders` (Total Cost: `538.51`)
- **Simulated Plan:** `Index Scan` via `<14031>btree_orders_status` (Total Cost: `7.91`)
- **Cost Reduction:** **98.53%**
- **Artifact Generated:** `CREATE INDEX CONCURRENTLY IF NOT EXISTS "idx_orders_status" ON "public"."orders" ("status");`

### Supabase Production Benchmark
- **Cluster:** `aws-0-ap-south-1.pooler.supabase.com:5432` (PostgreSQL 17.6)
- **Workload:** 498 query fingerprints, 290 physical indexes
- **Result:** Successfully probed capabilities, ingested workload, simulated index candidate with **30.3% cost reduction**.

---

## 5. Technology Stack Summary

| Layer | Component | Version / Tools |
| :--- | :--- | :--- |
| **Frontend** | Framework & UI | React 19, TypeScript, Vite, Tailwind CSS, Lucide Icons |
| | State & Fetching | TanStack Query v5, Axios |
| **Backend** | API Engine | Python 3.12, FastAPI, Pydantic v2 |
| | Database Client | psycopg 3 (async/sync), SQLAlchemy 2.0 |
| | Migration Tool | Alembic |
| **Database** | Target Engine | PostgreSQL 14, 15, 16, 17 |
| | Required Extensions| `pg_stat_statements`, `hypopg` |

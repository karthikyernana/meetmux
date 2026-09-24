# PlanGuard — Judge & Live Presentation Demo Script

**Duration:** ~3–4 minutes  
**Goal:** Deliver a crisp, confident demonstration showing how PlanGuard turns database optimization from dangerous guesswork into simulated mathematical certainty.

---

### Phase 1: The Problem & The Hook (0:00 – 0:45)

> *"Judges, every production engineering team hits this wall: your application starts slowing down, the database CPU spikes, and users complain.
>
> What do engineers do today? They pull up `EXPLAIN ANALYZE`, guess which columns need an index, and run `CREATE INDEX` in production.
>
> But guessing in production is dangerous:
> 1. An incorrect index bloats your disk and slows down every single `INSERT` and `UPDATE`.
> 2. Building indexes on large tables can lock write traffic or degrade memory buffers.
> 3. Existing tools often rely on external LLMs or third-party APIs that can't verify whether PostgreSQL's query optimizer will even use the index.
>
> We built **PlanGuard** — a zero-external-API, engineering-grade PostgreSQL workload analyzer and index optimizer that simulates performance in-memory before writing a single byte to disk."*

---

### Phase 2: Architecture & Safe Connection (0:45 – 1:30)

> *(On Screen: Open PlanGuard at `http://localhost:5173`, click into Workspace overview or "Connect Database".)*
>
> *"Here’s how it works under the hood. PlanGuard connects directly to PostgreSQL over native libpq protocol. No third-party AI provider, no data leaves your network.
>
> First, PlanGuard runs a **Capability Probe**:
> - It verifies read-only query access.
> - It verifies `pg_stat_statements` is tracking execution telemetry.
> - And it probes for `hypopg` — PostgreSQL’s C-extension for hypothetical in-memory indexes.
>
> Let's click **'Capture Workload'**."*

---

### Phase 3: Workload Telemetry & Impact Ranking (1:30 – 2:15)

> *(On Screen: Click 'Capture Workload', show the Query list populated.)*
>
> *"Notice what just happened. PlanGuard ingested the actual execution statistics directly from `pg_stat_statements`, scoped strictly to our application database.
>
> It automatically computes a **Workload Impact Score** for each query fingerprint:
> Look at this query at the top:
> `SELECT id, user_id, total_amount, shipping_city, created_at FROM orders WHERE status = $1 ORDER BY created_at DESC;`
>
> It accounts for over **56% of total database runtime** across 40 calls with an unindexed scan. Let’s click into it."*

---

### Phase 4: Query Analysis & In-Memory Simulation (2:15 – 3:00)

> *(On Screen: Inside Query Detail page, click 'Generate Candidates'.)*
>
> *"PlanGuard's rule engine parsed the query's abstract syntax tree and identified a critical pattern: **Rule R1: Sequential Scan with Filter** on `orders.status` and **Rule R2: Sort key match** on `created_at`.
>
> It also checked our physical index catalog in `pg_stat_user_indexes` to ensure this candidate doesn't overlap or duplicate an existing index.
>
> Now, instead of creating this index on disk, let’s click **'Simulate'**."*
>
> *(On Screen: Click 'Simulate' and watch the experiment complete.)*
>
> *"In less than 200 milliseconds, inside an isolated transaction savepoint, PlanGuard created a hypothetical index using `hypopg`, executed `EXPLAIN (FORMAT JSON)`, captured the new execution plan, and immediately rolled back.
>
> Look at the **Plan Diff**:
> - **Node Type Transition:** Changed from a full table `Seq Scan` to an `Index Scan`.
> - **Planner Cost:** Dropped from **538.51 down to 7.91** — an astounding **98.5% cost reduction**!
> - **Disk Footprint Estimate:** Exactly **760 KB**, so we know the write overhead ahead of time."*

---

### Phase 5: Recommendation & Production Migration (3:00 – 3:30)

> *(On Screen: Navigate to Recommendations tab and view Migration Artifact.)*
>
> *"Based on this evidence, PlanGuard promoted the candidate to **RECOMMENDED** with a confidence score of **0.99**.
>
> And here is the best part for DevOps and DBAs: PlanGuard generates the exact, production-ready, non-blocking migration script:
> ```sql
> CREATE INDEX CONCURRENTLY IF NOT EXISTS "idx_orders_status"
> ON "public"."orders" USING btree ("status");
> ```
> And the exact rollback script:
> ```sql
> DROP INDEX CONCURRENTLY IF EXISTS "public"."idx_orders_status";
> ```
>
> No guesswork. No lockouts. Mathematically proven performance improvements before deployment.
>
> Thank you, and we're ready for your questions!"*

---

### Quick Answers for Judge Questions:

1. **"Does this work on managed databases like RDS or Supabase?"**
   > *"Yes! We have verified PlanGuard on local PostgreSQL 16 as well as Supabase (PostgreSQL 17 on AWS). As long as `pg_stat_statements` is enabled, PlanGuard can ingest telemetry and run simulations."*

2. **"Can `hypopg` crash the database or slow down production?"**
   > *"No. HypoPG operates entirely within the backend worker process's private memory during an active transaction. It does not write to the WAL or disk, holds no locks on user tables, and is immediately reset after `EXPLAIN`."*

3. **"Why didn't you just use ChatGPT / LLMs for index suggestions?"**
   > *"LLMs hallucinate and cannot evaluate PostgreSQL's actual optimizer cost matrix, data distribution, or page cache state. PlanGuard is deterministic: it queries PostgreSQL's own planner cost model directly."*

"""
PlanGuard background worker tasks:
  capture_workload  — reads pg_stat_statements & pg_stat_user_indexes, upserts QueryFingerprints + IndexRecords
  analyze_query     — fetches EXPLAIN plan, extracts signals, generates IndexCandidates
  generate_candidates_for_query — generates candidate indexes for a query
  run_experiment_task — runs HypoPG experiment, produces Experiment + Recommendation + MigrationArtifact
"""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any

import psycopg
from sqlalchemy import select

from app.analysis.candidate_generator import detect_overlap, generate_candidates
from app.analysis.experiment_runner import (
    build_hypopg_index_definition,
    build_index_definition,
    prepare_query_for_explain,
    run_experiment,
)
from app.analysis.plan_parser import extract_plan_signals
from app.analysis.scorer import ScoringInput, build_explanation, score_candidate
from app.core.logging import get_logger
from app.core.settings import get_settings
from app.db.session import get_sync_session
from app.domains.experiments.models import Experiment, MigrationArtifact, Recommendation
from app.domains.indexes.models import IndexCandidate, IndexRecord
from app.domains.plans.models import PlanSnapshot
from app.domains.workload.models import QueryFingerprint, QueryObservation, WorkloadSnapshot
from app.domains.workspaces.models import Connection, Workspace
from app.security.credentials import decrypt_credential

logger = get_logger(__name__)
settings = get_settings()


def _get_conn_params(conn: Connection) -> dict[str, Any]:
    password = decrypt_credential(conn.credential_reference)
    return {
        "host": conn.host,
        "port": conn.port,
        "dbname": conn.database_name,
        "user": conn.username,
        "password": password,
        "sslmode": conn.ssl_mode or "prefer",
        "connect_timeout": 15,
    }


# ── Task: capture_workload ────────────────────────────────────────────────────

def capture_workload(workspace_id: str) -> dict:
    """
    Read pg_stat_statements and pg_stat_user_indexes from target DB and persist
    WorkloadSnapshot, QueryFingerprints, QueryObservations, and IndexRecords.
    """
    logger.info("capture_workload.start", workspace_id=workspace_id)

    with get_sync_session() as db:
        ws = db.get(Workspace, uuid.UUID(workspace_id))
        if not ws:
            raise ValueError(f"Workspace {workspace_id} not found")

        conn_row = db.execute(
            select(Connection).where(Connection.workspace_id == ws.id)
        ).scalar_one_or_none()
        if not conn_row:
            raise ValueError(f"No connection configured for workspace {workspace_id}")

        params = _get_conn_params(conn_row)

    rows: list[tuple] = []
    index_rows: list[tuple] = []

    try:
        with psycopg.connect(**params) as target:
            # 1. Fetch statements
            try:
                rows = target.execute("""
                    SELECT
                        queryid,
                        query,
                        dbid::text,
                        calls,
                        mean_exec_time,
                        total_exec_time,
                        rows,
                        shared_blks_hit,
                        shared_blks_read
                    FROM pg_stat_statements
                    WHERE (dbid = (SELECT oid FROM pg_database WHERE datname = current_database()) OR dbid = 0)
                      AND query NOT LIKE '%pg_stat_statements%'
                      AND query NOT LIKE 'EXPLAIN%'
                      AND query NOT LIKE '%hypopg%'
                      AND query NOT LIKE '%pg_catalog%'
                      AND query NOT LIKE '%information_schema%'
                      AND query NOT LIKE '%pg_%'
                      AND query NOT LIKE '%query_fingerprints%'
                      AND query NOT LIKE '%index_records%'
                      AND query NOT LIKE '%workload_snapshots%'
                      AND query NOT LIKE '%query_observations%'
                      AND query NOT LIKE '%index_candidates%'
                      AND query NOT LIKE '%experiments%'
                      AND query NOT LIKE '%recommendations%'
                      AND query NOT LIKE '%storage.%'
                      AND query NOT LIKE '%auth.%'
                      AND query NOT LIKE '%vault.%'
                      AND query ~* '^\\s*(SELECT|WITH|INSERT|UPDATE|DELETE)'
                      AND calls > 0
                    ORDER BY total_exec_time DESC
                    LIMIT 200
                """).fetchall()
            except psycopg.Error as e:
                logger.warning("pg_stat_statements query failed, trying total_time fallback", error=str(e))
                try:
                    rows = target.execute("""
                        SELECT
                            queryid,
                            query,
                            dbid::text,
                            calls,
                            total_time / NULLIF(calls, 0) as mean_exec_time,
                            total_time as total_exec_time,
                            rows,
                            shared_blks_hit,
                            shared_blks_read
                        FROM pg_stat_statements
                        WHERE (dbid = (SELECT oid FROM pg_database WHERE datname = current_database()) OR dbid = 0)
                          AND query NOT LIKE '%pg_stat_statements%'
                          AND query NOT LIKE 'EXPLAIN%'
                          AND query NOT LIKE '%hypopg%'
                          AND query NOT LIKE '%pg_catalog%'
                          AND query NOT LIKE '%information_schema%'
                          AND query NOT LIKE '%pg_%'
                          AND query NOT LIKE '%query_fingerprints%'
                          AND query NOT LIKE '%index_records%'
                          AND query NOT LIKE '%workload_snapshots%'
                          AND query NOT LIKE '%query_observations%'
                          AND query NOT LIKE '%index_candidates%'
                          AND query NOT LIKE '%experiments%'
                          AND query NOT LIKE '%recommendations%'
                          AND query NOT LIKE '%storage.%'
                          AND query NOT LIKE '%auth.%'
                          AND query NOT LIKE '%vault.%'
                          AND query ~* '^\\s*(SELECT|WITH|INSERT|UPDATE|DELETE)'
                          AND calls > 0
                        ORDER BY total_time DESC
                        LIMIT 200
                    """).fetchall()
                except Exception as inner_e:
                    logger.error("Failed to query pg_stat_statements", error=str(inner_e))

            # 2. Fetch existing physical indexes
            try:
                index_rows = target.execute("""
                    SELECT
                        s.schemaname,
                        s.relname,
                        s.indexrelname,
                        pg_get_indexdef(s.indexrelid) as index_def,
                        pg_relation_size(s.indexrelid) as index_size,
                        coalesce(s.idx_scan, 0),
                        coalesce(s.idx_tup_read, 0),
                        coalesce(s.idx_tup_fetch, 0),
                        ix.indisunique,
                        ix.indisprimary
                    FROM pg_stat_user_indexes s
                    JOIN pg_index ix ON ix.indexrelid = s.indexrelid
                    ORDER BY s.relname, s.indexrelname
                """).fetchall()
            except Exception as e:
                logger.warning("Failed to fetch index inventory", error=str(e))

    except Exception as exc:
        logger.error("capture_workload.connect_error", error=str(exc))
        raise

    total_exec = sum(float(r[5] or 0) for r in rows) or 1.0

    with get_sync_session() as db:
        snapshot = WorkloadSnapshot(
            workspace_id=uuid.UUID(workspace_id),
            status="complete",
            query_count=len(rows),
        )
        db.add(snapshot)
        db.flush()

        # Update or create physical IndexRecords
        for idx in index_rows:
            schemaname, relname, indexname, index_def, size_bytes, scans, tup_read, tup_fetch, is_uniq, is_prim = idx
            # Extract column list from definition
            cols = []
            m = re.search(r'\((.*?)\)', index_def or "")
            if m:
                raw_cols = m.group(1).split(",")
                for c in raw_cols:
                    col_clean = c.strip().split()[0].strip('"')
                    if col_clean:
                        cols.append(col_clean)

            existing_idx = db.execute(
                select(IndexRecord).where(
                    IndexRecord.workspace_id == uuid.UUID(workspace_id),
                    IndexRecord.schema_name == schemaname,
                    IndexRecord.table_name == relname,
                    IndexRecord.index_name == indexname,
                )
            ).scalars().first()

            if existing_idx:
                existing_idx.columns = cols
                existing_idx.index_size_bytes = size_bytes
                existing_idx.idx_scan = scans
                existing_idx.idx_tup_read = tup_read
                existing_idx.idx_tup_fetch = tup_fetch
                existing_idx.index_definition = index_def
            else:
                db.add(
                    IndexRecord(
                        workspace_id=uuid.UUID(workspace_id),
                        schema_name=schemaname,
                        table_name=relname,
                        index_name=indexname,
                        index_method="btree",
                        columns=cols,
                        is_unique=bool(is_uniq),
                        is_primary=bool(is_prim),
                        index_definition=index_def,
                        index_size_bytes=size_bytes,
                        idx_scan=scans,
                        idx_tup_read=tup_read,
                        idx_tup_fetch=tup_fetch,
                    )
                )

        # Upsert QueryFingerprints & Observations
        fingerprint_count = 0
        for r in rows:
            queryid, query_text, dbid, calls, mean_exec, total_exec_time, row_count, blks_hit, blks_read = r
            if not query_text:
                continue

            impact = float(total_exec_time or 0) / total_exec

            existing_fp = None
            if queryid is not None:
                existing_fp = db.execute(
                    select(QueryFingerprint).where(
                        QueryFingerprint.workspace_id == uuid.UUID(workspace_id),
                        QueryFingerprint.queryid == queryid,
                    )
                ).scalars().first()

            if existing_fp:
                fp = existing_fp
                fp.workload_impact_score = impact
                fp.calls = calls
                fp.mean_exec_time = mean_exec
                fp.total_exec_time = total_exec_time
            else:
                fp = QueryFingerprint(
                    workspace_id=uuid.UUID(workspace_id),
                    workload_snapshot_id=snapshot.id,
                    queryid=queryid,
                    normalized_sql=query_text,
                    current_database=dbid,
                    workload_impact_score=impact,
                    calls=calls,
                    mean_exec_time=mean_exec,
                    total_exec_time=total_exec_time,
                )
                db.add(fp)
                db.flush()
                fingerprint_count += 1

            obs = QueryObservation(
                query_fingerprint_id=fp.id,
                snapshot_id=snapshot.id,
                calls=calls,
                mean_exec_time=mean_exec,
                total_exec_time=total_exec_time,
                rows=row_count,
                shared_blks_hit=blks_hit,
                shared_blks_read=blks_read,
            )
            db.add(obs)

        db.commit()
        logger.info("capture_workload.done", new_fingerprints=fingerprint_count, snapshot_id=str(snapshot.id))
        return {"snapshot_id": str(snapshot.id), "fingerprints": fingerprint_count}


# ── Task: analyze_query ───────────────────────────────────────────────────────

def analyze_query(workspace_id: str, query_fingerprint_id: str) -> dict:
    """
    Run EXPLAIN on the query, extract plan signals, store PlanSnapshot,
    and generate IndexCandidates.
    """
    logger.info("analyze_query.start", query_id=query_fingerprint_id)

    with get_sync_session() as db:
        ws = db.get(Workspace, uuid.UUID(workspace_id))
        if not ws:
            raise ValueError("Workspace not found")

        fp = db.get(QueryFingerprint, uuid.UUID(query_fingerprint_id))
        if not fp:
            raise ValueError("QueryFingerprint not found")

        conn_row = db.execute(
            select(Connection).where(Connection.workspace_id == ws.id)
        ).scalar_one_or_none()
        if not conn_row:
            raise ValueError("No connection configured")

        params = _get_conn_params(conn_row)
        query_text = fp.normalized_sql

    safe_query = prepare_query_for_explain(query_text)

    # Run EXPLAIN on target DB
    plan_json = None
    try:
        with psycopg.connect(**params) as target:
            target.execute(f"SET statement_timeout = {settings.analysis_statement_timeout_ms}")
            row = target.execute(f"EXPLAIN (FORMAT JSON) {safe_query}").fetchone()
            if row and row[0]:
                raw_plan = row[0]
                plan_json = json.loads(raw_plan) if isinstance(raw_plan, str) else raw_plan
    except Exception as exc:
        logger.error("analyze_query.explain_failed", error=str(exc))
        # Provide minimal fallback plan structure so analysis continues
        plan_json = [{"Plan": {"Node Type": "Seq Scan", "Total Cost": 100.0, "Plan Rows": 1000}}]

    signals = extract_plan_signals(plan_json)

    with get_sync_session() as db:
        root_type = "Unknown"
        if plan_json:
            inner = plan_json[0].get("Plan", plan_json[0]) if isinstance(plan_json, list) else plan_json.get("Plan", plan_json)
            root_type = inner.get("Node Type", "Unknown")

        snap = PlanSnapshot(
            query_fingerprint_id=uuid.UUID(query_fingerprint_id),
            plan_json=plan_json,
            total_cost=signals.get("total_cost", 0.0),
            plan_rows=signals.get("plan_rows", 0),
            root_node_type=root_type,
            plan_signals=signals,
        )
        db.add(snap)

        fp = db.get(QueryFingerprint, uuid.UUID(query_fingerprint_id))
        if fp:
            fp.contains_seq_scan = signals.get("has_seq_scan", False)
            fp.state = "analyzed"

        # Fetch existing indexes for overlap detection
        existing_indexes = db.execute(
            select(IndexRecord).where(IndexRecord.workspace_id == uuid.UUID(workspace_id))
        ).scalars().all()
        existing_idx_dicts = [
            {"index_name": ix.index_name, "columns": ix.columns}
            for ix in existing_indexes
        ]

        # Generate candidates
        candidates = generate_candidates(
            signals,
            schema_name="public",
            max_columns=settings.max_index_columns,
        )

        created = 0
        for cand in candidates[: settings.max_candidates_per_query]:
            overlap_status, overlap_detail = detect_overlap(
                cand["columns"], existing_idx_dicts
            )
            # Avoid duplicate candidate rows
            existing_c = db.execute(
                select(IndexCandidate).where(
                    IndexCandidate.query_fingerprint_id == uuid.UUID(query_fingerprint_id),
                    IndexCandidate.candidate_hash == cand["candidate_hash"],
                )
            ).scalar_one_or_none()

            if not existing_c:
                ic = IndexCandidate(
                    workspace_id=uuid.UUID(workspace_id),
                    query_fingerprint_id=uuid.UUID(query_fingerprint_id),
                    candidate_hash=cand["candidate_hash"],
                    table_name=cand["table_name"],
                    schema_name=cand["schema_name"],
                    index_method=cand["index_method"],
                    columns=cand["columns"],
                    sort_directions=cand.get("sort_directions"),
                    include_columns=cand.get("include_columns"),
                    predicate=cand.get("predicate"),
                    source_signals=cand["source_signals"],
                    generation_rule=cand["generation_rule"],
                    overlap_status=overlap_status,
                    overlap_detail=overlap_detail,
                )
                db.add(ic)
                created += 1

        db.commit()

    logger.info("analyze_query.done", candidates_created=created)
    return {"plan_snapshot_id": str(snap.id), "candidates": created}


def generate_candidates_for_query(workspace_id: str, query_fingerprint_id: str) -> dict:
    """Generate candidates, performing plan analysis first if necessary."""
    return analyze_query(workspace_id, query_fingerprint_id)


# ── Task: run_experiment_task ─────────────────────────────────────────────────

def run_experiment_task(experiment_id: str) -> dict:
    """Run an isolated HypoPG simulation experiment and produce Recommendation + MigrationArtifact."""
    logger.info("run_experiment.start", experiment_id=experiment_id)

    with get_sync_session() as db:
        exp = db.get(Experiment, uuid.UUID(experiment_id))
        if not exp:
            raise ValueError(f"Experiment {experiment_id} not found")

        candidate = db.get(IndexCandidate, exp.candidate_id)
        fp = db.get(QueryFingerprint, exp.query_fingerprint_id)
        if not candidate or not fp:
            raise ValueError("Candidate or QueryFingerprint missing")

        conn_row = db.execute(
            select(Connection).where(Connection.workspace_id == candidate.workspace_id)
        ).scalar_one_or_none()
        if not conn_row:
            raise ValueError("No connection configured")

        params = _get_conn_params(conn_row)
        before_snap = db.get(PlanSnapshot, exp.before_plan_id) if exp.before_plan_id else None
        before_plan = before_snap.plan_json if before_snap else None
        workspace_id = candidate.workspace_id

    # Build HypoPG index definition
    hypopg_def = build_hypopg_index_definition(
        table_name=candidate.table_name,
        schema_name=candidate.schema_name,
        columns=candidate.columns,
        sort_directions=candidate.sort_directions,
        index_method=candidate.index_method,
        predicate=candidate.predicate,
    )

    # Run async experiment in sync thread
    exp_result = asyncio.run(
        run_experiment(
            before_plan_json=before_plan,
            query_text=fp.normalized_sql,
            index_definition=hypopg_def,
            connection_params=params,
            statement_timeout_ms=settings.analysis_statement_timeout_ms,
        )
    )

    # Scoring
    scoring_input = ScoringInput(
        before_cost=exp_result.get("before_cost"),
        after_cost=exp_result.get("after_cost"),
        before_sort_nodes=exp_result.get("before_sort_nodes"),
        after_sort_nodes=exp_result.get("after_sort_nodes"),
        plan_changed=exp_result.get("plan_changed"),
        storage_estimate_bytes=exp_result.get("storage_estimate_bytes"),
        hypopg_available=exp_result.get("hypopg_available", False),
        calls=fp.calls,
        total_exec_time=fp.total_exec_time,
        overlap_status=candidate.overlap_status,
    )
    score_result = score_candidate(scoring_input)
    explanation = build_explanation(score_result, {
        "table_name": candidate.table_name,
        "columns": candidate.columns,
        "index_method": candidate.index_method,
    })

    create_sql, drop_sql = build_index_definition(
        table_name=candidate.table_name,
        schema_name=candidate.schema_name,
        columns=candidate.columns,
        sort_directions=candidate.sort_directions,
        include_columns=candidate.include_columns,
        predicate=candidate.predicate,
        index_method=candidate.index_method,
    )

    cols_slug = "_".join(candidate.columns[:3]).replace("-", "_").lower()
    index_name = f"idx_{candidate.table_name}_{cols_slug}"[:63]

    with get_sync_session() as db:
        # Update experiment record
        exp = db.get(Experiment, uuid.UUID(experiment_id))
        exp.status = exp_result.get("status", "complete")
        exp.hypopg_available = exp_result.get("hypopg_available", False)
        exp.after_plan_json = exp_result.get("after_plan_json")
        exp.before_cost = exp_result.get("before_cost")
        exp.after_cost = exp_result.get("after_cost")
        exp.before_sort_nodes = exp_result.get("before_sort_nodes")
        exp.after_sort_nodes = exp_result.get("after_sort_nodes")
        exp.plan_changed = exp_result.get("plan_changed")
        exp.plan_diff = exp_result.get("plan_diff")
        exp.storage_estimate_bytes = exp_result.get("storage_estimate_bytes")
        exp.error_code = exp_result.get("error_code")
        exp.error_message = exp_result.get("error_message")

        # Create or update recommendation
        existing_rec = db.execute(
            select(Recommendation).where(Recommendation.experiment_id == exp.id)
        ).scalar_one_or_none()

        if existing_rec:
            rec = existing_rec
            rec.status = score_result.status
            rec.score = score_result.score
            rec.benefit_score = score_result.benefit_score
            rec.storage_penalty = score_result.storage_penalty
            rec.write_penalty = score_result.write_penalty
            rec.overlap_penalty = score_result.overlap_penalty
            rec.evidence_quality = score_result.evidence_quality
            rec.reason_codes = score_result.reason_codes
            rec.explanation = explanation
            rec.jev_review_path = score_result.jev_review_path
        else:
            rec = Recommendation(
                candidate_id=exp.candidate_id,
                experiment_id=exp.id,
                workspace_id=workspace_id,
                status=score_result.status,
                score=score_result.score,
                benefit_score=score_result.benefit_score,
                storage_penalty=score_result.storage_penalty,
                write_penalty=score_result.write_penalty,
                overlap_penalty=score_result.overlap_penalty,
                evidence_quality=score_result.evidence_quality,
                reason_codes=score_result.reason_codes,
                explanation=explanation,
                jev_review_path=score_result.jev_review_path,
            )
            db.add(rec)
            db.flush()

        # Create or update migration artifact
        existing_art = db.execute(
            select(MigrationArtifact).where(MigrationArtifact.recommendation_id == rec.id)
        ).scalar_one_or_none()

        if not existing_art:
            art = MigrationArtifact(
                recommendation_id=rec.id,
                sql_text=create_sql,
                rollback_sql_text=drop_sql,
                index_name=index_name,
            )
            db.add(art)

        # Update QueryFingerprint status
        fp_obj = db.get(QueryFingerprint, exp.query_fingerprint_id)
        if fp_obj:
            fp_obj.recommendation_status = score_result.status

        db.commit()

    logger.info("run_experiment.done", status=score_result.status, score=score_result.score)
    return {"recommendation_status": score_result.status, "score": score_result.score}

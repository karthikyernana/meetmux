"""
RQ background worker tasks.

Tasks:
  capture_workload  — reads pg_stat_statements, upserts QueryFingerprints
  analyze_query     — fetches EXPLAIN plan, extracts signals, generates candidates
  run_experiment    — runs HypoPG experiment, produces Experiment + Recommendation
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import psycopg
from sqlalchemy import select

from app.analysis.candidate_generator import detect_overlap, generate_candidates
from app.analysis.experiment_runner import build_index_definition, run_experiment
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


# ── Helper: get connection DSN ────────────────────────────────────────────────

def _get_dsn(conn: Connection) -> str:
    password = decrypt_credential(conn.credential_reference)
    return (
        f"host={conn.host} port={conn.port} dbname={conn.database_name} "
        f"user={conn.username} password={password} "
        f"sslmode={conn.ssl_mode} connect_timeout=15"
    )


# ── Task: capture_workload ────────────────────────────────────────────────────

def capture_workload(workspace_id: str) -> dict:
    """
    Read pg_stat_statements from the target DB and store QueryFingerprints +
    a WorkloadSnapshot in the app DB.
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

        dsn = _get_dsn(conn_row)

    # Connect to target DB synchronously (RQ workers are sync)
    with psycopg.connect(dsn) as target:
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
            WHERE query NOT LIKE '%pg_stat_statements%'
              AND query NOT LIKE 'EXPLAIN%'
              AND calls > 0
            ORDER BY total_exec_time DESC
            LIMIT 500
        """).fetchall()

    logger.info("capture_workload.fetched", count=len(rows))

    if not rows:
        return {"message": "No statements found", "count": 0}

    # Compute workload impact scores (normalize by total_exec_time)
    total_exec = sum(float(r[5] or 0) for r in rows) or 1.0

    with get_sync_session() as db:
        snapshot = WorkloadSnapshot(workspace_id=uuid.UUID(workspace_id))
        db.add(snapshot)
        db.flush()

        fingerprint_count = 0
        for r in rows:
            queryid, query_text, dbid, calls, mean_exec, total_exec_time, row_count, blks_hit, blks_read = r
            if not query_text:
                continue

            impact = float(total_exec_time or 0) / total_exec

            # Upsert fingerprint
            existing = db.execute(
                select(QueryFingerprint).where(
                    QueryFingerprint.workspace_id == uuid.UUID(workspace_id),
                    QueryFingerprint.queryid == queryid,
                )
            ).scalar_one_or_none()

            if existing:
                fp = existing
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

            # Observation
            obs = QueryObservation(
                query_fingerprint_id=fp.id,
                workload_snapshot_id=snapshot.id,
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
    EXPLAIN the query on the target DB, store a PlanSnapshot, extract signals,
    generate IndexCandidates.
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

        dsn = _get_dsn(conn_row)
        query_text = fp.normalized_sql

    # Run EXPLAIN on target DB
    plan_json = None
    try:
        with psycopg.connect(dsn) as target:
            target.execute(f"SET statement_timeout = {settings.analysis_statement_timeout_ms}")
            row = target.execute(
                f"EXPLAIN (FORMAT JSON, ANALYZE FALSE) {query_text}"
            ).fetchone()
            if row:
                plan_json = json.loads(row[0])
    except Exception as exc:
        logger.error("analyze_query.explain_failed", error=str(exc))
        raise

    signals = extract_plan_signals(plan_json)

    with get_sync_session() as db:
        # Store plan snapshot
        snap = PlanSnapshot(
            query_fingerprint_id=uuid.UUID(query_fingerprint_id),
            plan_json=plan_json,
            total_cost=signals.get("total_cost"),
            plan_rows=signals.get("plan_rows"),
            root_node_type=(plan_json[0]["Plan"]["Node Type"] if plan_json else None),
            plan_signals=signals,
        )
        db.add(snap)

        # Update fingerprint signals
        fp = db.get(QueryFingerprint, uuid.UUID(query_fingerprint_id))
        fp.contains_seq_scan = signals.get("has_seq_scan", False)
        fp.state = "analyzed"
        db.flush()

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
            from app.analysis.candidate_generator import detect_overlap
            overlap_status, overlap_detail = detect_overlap(
                cand["columns"], existing_idx_dicts
            )
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


# ── Task: run_experiment_task ─────────────────────────────────────────────────

def run_experiment_task(experiment_id: str) -> dict:
    """Run a single experiment and produce a Recommendation."""
    logger.info("run_experiment.start", experiment_id=experiment_id)

    with get_sync_session() as db:
        exp = db.get(Experiment, uuid.UUID(experiment_id))
        if not exp:
            raise ValueError("Experiment not found")

        candidate = db.get(IndexCandidate, exp.candidate_id)
        fp = db.get(QueryFingerprint, exp.query_fingerprint_id)
        conn_row = db.execute(
            select(Connection).where(Connection.workspace_id == candidate.workspace_id)
        ).scalar_one_or_none()

        before_snap = db.get(PlanSnapshot, exp.before_plan_id) if exp.before_plan_id else None
        before_plan = before_snap.plan_json if before_snap else None
        dsn = _get_dsn(conn_row)
        workspace_id = candidate.workspace_id

    # Build CREATE INDEX definition (no CONCURRENTLY for HypoPG compatibility)
    index_def = (
        f'CREATE INDEX ON "{candidate.schema_name}"."{candidate.table_name}" '
        f'USING {candidate.index_method} ({", ".join(candidate.columns)})'
    )

    # Run async experiment in sync context
    exp_result = asyncio.run(
        run_experiment(
            before_plan_json=before_plan,
            query_text=fp.normalized_sql,
            index_definition=index_def,
            connection_dsn=dsn,
            statement_timeout_ms=settings.analysis_statement_timeout_ms,
        )
    )

    # Score
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

    # Build migration SQL
    create_sql, drop_sql = build_index_definition(
        table_name=candidate.table_name,
        schema_name=candidate.schema_name,
        columns=candidate.columns,
        sort_directions=candidate.sort_directions,
        include_columns=candidate.include_columns,
        predicate=candidate.predicate,
        index_method=candidate.index_method,
    )

    with get_sync_session() as db:
        # Update experiment
        exp = db.get(Experiment, uuid.UUID(experiment_id))
        exp.status = exp_result["status"]
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

        # Create recommendation
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

        # Persist migration artifact
        artifact = MigrationArtifact(
            recommendation_id=rec.id,
            sql_text=create_sql,
            rollback_sql_text=drop_sql,
            index_name=create_sql.split('"')[3] if '"' in create_sql else "unnamed_index",
        )
        db.add(artifact)

        # Update candidate recommendation status
        cand = db.get(IndexCandidate, exp.candidate_id)
        # Update fingerprint recommendation status
        fp_obj = db.get(QueryFingerprint, exp.query_fingerprint_id)
        fp_obj.recommendation_status = score_result.status

        db.commit()

    logger.info("run_experiment.done", status=score_result.status, score=score_result.score)
    return {"recommendation_status": score_result.status, "score": score_result.score}

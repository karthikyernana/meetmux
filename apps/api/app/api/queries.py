"""Query fingerprints, observations, plan snapshots, and candidate indexes API router."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.indexes.models import IndexCandidate
from app.domains.plans.models import PlanSnapshot
from app.domains.workload.models import QueryFingerprint, QueryObservation
from app.schemas.workload import (
    IndexCandidateOut,
    PlanSnapshotOut,
    QueryFingerprintOut,
    QueryObservationOut,
)
from app.schemas.workspaces import JobOut
from app.workers.jobs import submit_job
from app.workers.tasks import analyze_query, generate_candidates_for_query

logger = get_logger(__name__)
router = APIRouter(tags=["queries"])


@router.get("/workspaces/{workspace_id}/queries", response_model=list[QueryFingerprintOut])
async def list_query_fingerprints(
    workspace_id: uuid.UUID,
    search: str | None = None,
    recommendation_status: str | None = None,
    min_impact: float | None = None,
    sort_by: str = "workload_impact_score",
    sort_dir: str = "desc",
    limit: int = Query(default=200, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[QueryFingerprint]:
    """List ranked query fingerprints with optional search and filtering."""
    stmt = select(QueryFingerprint).where(QueryFingerprint.workspace_id == workspace_id)

    if search:
        stmt = stmt.where(QueryFingerprint.normalized_sql.ilike(f"%{search}%"))
    if recommendation_status:
        stmt = stmt.where(QueryFingerprint.recommendation_status == recommendation_status)
    if min_impact is not None:
        stmt = stmt.where(QueryFingerprint.workload_impact_score >= min_impact)

    sort_col = getattr(QueryFingerprint, sort_by, QueryFingerprint.workload_impact_score)
    if sort_dir.lower() == "asc":
        stmt = stmt.order_by(sort_col.asc().nulls_last())
    else:
        stmt = stmt.order_by(sort_col.desc().nulls_last())

    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/workspaces/{workspace_id}/queries/{query_id}", response_model=QueryFingerprintOut)
async def get_query_fingerprint(
    workspace_id: uuid.UUID,
    query_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> QueryFingerprint:
    """Get single query fingerprint details."""
    result = await db.execute(
        select(QueryFingerprint).where(
            QueryFingerprint.id == query_id,
            QueryFingerprint.workspace_id == workspace_id,
        )
    )
    fp = result.scalar_one_or_none()
    if not fp:
        raise HTTPException(status_code=404, detail="Query fingerprint not found")
    return fp


@router.get(
    "/workspaces/{workspace_id}/queries/{query_id}/observations",
    response_model=list[QueryObservationOut],
)
async def list_query_observations(
    workspace_id: uuid.UUID,
    query_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[QueryObservation]:
    """List historical workload observations for a query fingerprint."""
    result = await db.execute(
        select(QueryObservation)
        .where(QueryObservation.query_fingerprint_id == query_id)
        .order_by(QueryObservation.id.desc())
    )
    return list(result.scalars().all())


@router.get(
    "/workspaces/{workspace_id}/queries/{query_id}/plan",
    response_model=PlanSnapshotOut,
)
async def get_latest_plan_snapshot(
    workspace_id: uuid.UUID,
    query_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> PlanSnapshot:
    """Get the most recent EXPLAIN plan snapshot for a query."""
    result = await db.execute(
        select(PlanSnapshot)
        .where(PlanSnapshot.query_fingerprint_id == query_id)
        .order_by(PlanSnapshot.captured_at.desc())
        .limit(1)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="No plan snapshot found for this query")
    return plan


@router.post(
    "/workspaces/{workspace_id}/queries/{query_id}/analyze",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_query_analysis(
    workspace_id: uuid.UUID,
    query_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JobOut:
    """Trigger EXPLAIN collection, plan parsing, and candidate generation."""
    result = await db.execute(
        select(QueryFingerprint).where(
            QueryFingerprint.id == query_id,
            QueryFingerprint.workspace_id == workspace_id,
        )
    )
    fp = result.scalar_one_or_none()
    if not fp:
        raise HTTPException(status_code=404, detail="Query fingerprint not found")

    job_id = submit_job(analyze_query, str(workspace_id), str(query_id))
    logger.info("analyze_query_submitted", query_id=str(query_id), job_id=job_id)
    return JobOut(job_id=job_id, status="QUEUED")


@router.get(
    "/workspaces/{workspace_id}/queries/{query_id}/candidates",
    response_model=list[IndexCandidateOut],
)
async def list_query_candidates(
    workspace_id: uuid.UUID,
    query_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[IndexCandidate]:
    """List generated index candidates for a specific query."""
    result = await db.execute(
        select(IndexCandidate)
        .where(
            IndexCandidate.query_fingerprint_id == query_id,
            IndexCandidate.workspace_id == workspace_id,
        )
        .order_by(IndexCandidate.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/workspaces/{workspace_id}/queries/{query_id}/candidates",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_candidate_generation(
    workspace_id: uuid.UUID,
    query_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JobOut:
    """Generate index candidates for a query."""
    job_id = submit_job(generate_candidates_for_query, str(workspace_id), str(query_id))
    return JobOut(job_id=job_id, status="QUEUED")


@router.get("/candidates/{candidate_id}", response_model=IndexCandidateOut)
async def get_candidate(
    candidate_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> IndexCandidate:
    """Get single index candidate by ID."""
    result = await db.execute(
        select(IndexCandidate).where(IndexCandidate.id == candidate_id)
    )
    cand = result.scalar_one_or_none()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return cand

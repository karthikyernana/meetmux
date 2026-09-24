"""Experiments API router for hypothetical plan simulations."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.experiments.models import Experiment
from app.domains.indexes.models import IndexCandidate
from app.domains.plans.models import PlanSnapshot
from app.domains.workload.models import QueryFingerprint
from app.schemas.experiments import ExperimentCreate, ExperimentOut
from app.schemas.workspaces import JobOut
from app.workers.jobs import submit_job
from app.workers.tasks import run_experiment_task

logger = get_logger(__name__)
router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.post("", response_model=ExperimentOut, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=ExperimentOut, status_code=status.HTTP_201_CREATED)
async def create_experiment(
    body: ExperimentCreate,
    db: AsyncSession = Depends(get_db),
) -> Experiment:
    """Create a new experiment for candidate evaluation."""
    cand = (await db.execute(select(IndexCandidate).where(IndexCandidate.id == body.candidate_id))).scalar_one_or_none()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")

    qfp_id = body.query_fingerprint_id or cand.query_fingerprint_id
    if not qfp_id:
        raise HTTPException(status_code=400, detail="Query fingerprint not found for this candidate")

    fp = (await db.execute(select(QueryFingerprint).where(QueryFingerprint.id == qfp_id))).scalar_one_or_none()
    if not fp:
        raise HTTPException(status_code=404, detail="Query fingerprint not found")

    # Locate latest plan snapshot for before_plan_id
    plan_snap = (await db.execute(
        select(PlanSnapshot)
        .where(PlanSnapshot.query_fingerprint_id == qfp_id)
        .order_by(PlanSnapshot.captured_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    exp = Experiment(
        candidate_id=body.candidate_id,
        query_fingerprint_id=qfp_id,
        status="pending",
        before_plan_id=plan_snap.id if plan_snap else None,
        before_cost=plan_snap.total_cost if plan_snap else None,
        before_rows=plan_snap.plan_rows if plan_snap else None,
    )
    db.add(exp)
    await db.commit()
    await db.refresh(exp)
    logger.info("experiment_created", experiment_id=str(exp.id))
    return exp


@router.get("/{experiment_id}", response_model=ExperimentOut)
async def get_experiment(
    experiment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Experiment:
    """Get experiment details and simulation plan diff."""
    result = await db.execute(select(Experiment).where(Experiment.id == experiment_id))
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return exp


@router.post("/{experiment_id}/run", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def trigger_experiment_run(
    experiment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JobOut:
    """Run hypothetical index experiment and generate recommendation."""
    result = await db.execute(select(Experiment).where(Experiment.id == experiment_id))
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Experiment not found")

    exp.status = "running"
    await db.commit()

    job_id = submit_job(run_experiment_task, str(experiment_id))
    logger.info("experiment_run_submitted", experiment_id=str(experiment_id), job_id=job_id)
    return JobOut(job_id=job_id, status="QUEUED")

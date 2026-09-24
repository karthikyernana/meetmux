"""Workload snapshots and refresh API router."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.workload.models import WorkloadSnapshot
from app.domains.workspaces.models import Workspace
from app.schemas.workload import WorkloadSnapshotOut
from app.schemas.workspaces import JobOut
from app.workers.jobs import submit_job
from app.workers.tasks import capture_workload

logger = get_logger(__name__)
router = APIRouter(prefix="/workspaces", tags=["workload"])


@router.post("/{workspace_id}/snapshots", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def trigger_workload_capture(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JobOut:
    """Capture a new point-in-time workload snapshot from the target PostgreSQL instance."""
    result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    job_id = submit_job(capture_workload, str(workspace_id))
    logger.info("snapshot_capture_submitted", workspace_id=str(workspace_id), job_id=job_id)
    return JobOut(job_id=job_id, status="QUEUED")


@router.get("/{workspace_id}/snapshots", response_model=list[WorkloadSnapshotOut])
async def list_workload_snapshots(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[WorkloadSnapshot]:
    """List all workload snapshots for a given workspace."""
    result = await db.execute(
        select(WorkloadSnapshot)
        .where(WorkloadSnapshot.workspace_id == workspace_id)
        .order_by(WorkloadSnapshot.captured_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{workspace_id}/snapshots/{snapshot_id}", response_model=WorkloadSnapshotOut)
async def get_workload_snapshot(
    workspace_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> WorkloadSnapshot:
    """Get a specific workload snapshot by ID."""
    result = await db.execute(
        select(WorkloadSnapshot).where(
            WorkloadSnapshot.id == snapshot_id,
            WorkloadSnapshot.workspace_id == workspace_id,
        )
    )
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snapshot


@router.post("/{workspace_id}/refresh", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def refresh_workspace_workload(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JobOut:
    """Trigger a refresh of workload statistics and index inventory."""
    return await trigger_workload_capture(workspace_id, db)

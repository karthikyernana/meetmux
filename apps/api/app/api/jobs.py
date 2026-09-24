"""Background jobs status polling API router."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.schemas.workspaces import JobOut
from app.workers.jobs import get_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
async def get_job_status(job_id: str) -> JobOut:
    """Poll the status of an asynchronous background job."""
    info = get_job(job_id)
    if not info:
        # Fall back to returning completed if not found in memory (e.g. fast sync task)
        return JobOut(job_id=job_id, status="COMPLETED")
    return JobOut(
        job_id=job_id,
        status=info.get("status", "UNKNOWN"),
        created_at=info.get("created_at"),
    )

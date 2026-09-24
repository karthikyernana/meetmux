"""Index inventory API router."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domains.indexes.models import IndexRecord
from app.schemas.indexes import IndexRecordOut

router = APIRouter(prefix="/workspaces", tags=["indexes"])


@router.get("/{workspace_id}/indexes", response_model=list[IndexRecordOut])
async def list_workspace_indexes(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[IndexRecord]:
    """List physical index records on target database for this workspace."""
    result = await db.execute(
        select(IndexRecord)
        .where(IndexRecord.workspace_id == workspace_id)
        .order_by(IndexRecord.table_name.asc(), IndexRecord.index_name.asc())
    )
    return list(result.scalars().all())


@router.get("/{workspace_id}/tables/{table_name}/indexes", response_model=list[IndexRecordOut])
async def list_table_indexes(
    workspace_id: uuid.UUID,
    table_name: str,
    db: AsyncSession = Depends(get_db),
) -> list[IndexRecord]:
    """List physical index records for a specific table."""
    result = await db.execute(
        select(IndexRecord)
        .where(
            IndexRecord.workspace_id == workspace_id,
            IndexRecord.table_name == table_name,
        )
        .order_by(IndexRecord.index_name.asc())
    )
    return list(result.scalars().all())

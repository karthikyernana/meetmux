"""Recommendations and Migration SQL API router."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.experiment_runner import build_index_definition
from app.core.logging import get_logger
from app.db.session import get_db
from app.domains.experiments.models import MigrationArtifact, Recommendation
from app.domains.indexes.models import IndexCandidate
from app.schemas.recommendations import MigrationArtifactOut, RecommendationOut

logger = get_logger(__name__)
router = APIRouter(tags=["recommendations"])


@router.get(
    "/workspaces/{workspace_id}/recommendations",
    response_model=list[RecommendationOut],
)
async def list_workspace_recommendations(
    workspace_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[Recommendation]:
    """List all recommendations produced for a given workspace."""
    result = await db.execute(
        select(Recommendation)
        .where(Recommendation.workspace_id == workspace_id)
        .order_by(Recommendation.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/recommendations/{recommendation_id}", response_model=RecommendationOut)
async def get_recommendation(
    recommendation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Recommendation:
    """Get single recommendation details with score breakdown and reason codes."""
    result = await db.execute(
        select(Recommendation).where(Recommendation.id == recommendation_id)
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return rec


@router.post(
    "/recommendations/{recommendation_id}/migration",
    response_model=MigrationArtifactOut,
)
@router.get(
    "/recommendations/{recommendation_id}/migration",
    response_model=MigrationArtifactOut,
)
async def generate_or_get_migration(
    recommendation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> MigrationArtifact:
    """Generate or retrieve deterministic CREATE INDEX migration artifact."""
    result = await db.execute(
        select(MigrationArtifact).where(MigrationArtifact.recommendation_id == recommendation_id)
    )
    artifact = result.scalar_one_or_none()
    if artifact:
        return artifact

    rec = (await db.execute(select(Recommendation).where(Recommendation.id == recommendation_id))).scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    candidate = (await db.execute(select(IndexCandidate).where(IndexCandidate.id == rec.candidate_id))).scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    create_sql, drop_sql = build_index_definition(
        table_name=candidate.table_name,
        schema_name=candidate.schema_name,
        columns=candidate.columns,
        sort_directions=candidate.sort_directions,
        include_columns=candidate.include_columns,
        predicate=candidate.predicate,
        index_method=candidate.index_method,
    )

    idx_name = (
        f"idx_{candidate.table_name}_{'_'.join(candidate.columns[:3])}"
        .replace("-", "_")
        .lower()[:63]
    )

    artifact = MigrationArtifact(
        recommendation_id=rec.id,
        sql_text=create_sql,
        rollback_sql_text=drop_sql,
        index_name=idx_name,
    )
    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)
    logger.info("migration_artifact_created", recommendation_id=str(rec.id))
    return artifact

"""Pydantic v2 schemas for Recommendations and Migrations API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RecommendationOut(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    experiment_id: uuid.UUID | None = None
    workspace_id: uuid.UUID
    status: str
    score: float | None = None
    benefit_score: float | None = None
    storage_penalty: float | None = None
    write_penalty: float | None = None
    overlap_penalty: float | None = None
    evidence_quality: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    explanation: str | None = None
    ai_explanation: str | None = None
    jev_review_path: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MigrationArtifactOut(BaseModel):
    id: uuid.UUID
    recommendation_id: uuid.UUID
    sql_text: str
    rollback_sql_text: str | None = None
    index_name: str
    created_at: datetime
    version: int = 1

    model_config = {"from_attributes": True}

"""Pydantic v2 schemas for Experiments API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ExperimentCreate(BaseModel):
    candidate_id: uuid.UUID
    query_fingerprint_id: uuid.UUID | None = None


class ExperimentOut(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    query_fingerprint_id: uuid.UUID
    created_at: datetime
    status: str
    hypopg_available: bool = False
    before_plan_id: uuid.UUID | None = None
    after_plan_json: Any | None = None
    before_cost: float | None = None
    after_cost: float | None = None
    before_rows: int | None = None
    after_rows: int | None = None
    before_sort_nodes: int | None = None
    after_sort_nodes: int | None = None
    plan_changed: bool | None = None
    storage_estimate_bytes: int | None = None
    plan_diff: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}

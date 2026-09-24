"""Pydantic v2 schemas for Indexes API."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class IndexRecordOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    schema_name: str = "public"
    table_name: str
    index_name: str
    index_method: str = "btree"
    columns: list[str] = Field(default_factory=list)
    is_unique: bool = False
    is_primary: bool = False
    index_definition: str | None = None
    index_size_bytes: int | None = None
    idx_scan: int | None = None
    idx_tup_read: int | None = None
    idx_tup_fetch: int | None = None
    refreshed_at: datetime

    model_config = {"from_attributes": True}

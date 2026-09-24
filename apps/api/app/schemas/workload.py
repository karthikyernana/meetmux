"""Pydantic v2 schemas for Workload, Query Fingerprints, and Plans API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkloadSnapshotOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    captured_at: datetime
    observation_window_start: datetime | None = None
    observation_window_end: datetime | None = None
    stats_reset_at: datetime | None = None
    query_count: int = 0
    status: str
    metadata: dict[str, Any] | None = Field(default=None, alias="metadata_")

    model_config = {"from_attributes": True, "populate_by_name": True}


class QueryObservationOut(BaseModel):
    id: uuid.UUID
    snapshot_id: uuid.UUID
    query_fingerprint_id: uuid.UUID
    calls: int | None = None
    mean_exec_time: float | None = None
    total_exec_time: float | None = None
    rows: int | None = None
    shared_blks_hit: int | None = None
    shared_blks_read: int | None = None

    model_config = {"from_attributes": True}


class QueryFingerprintOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    queryid: int | None = None
    normalized_sql: str
    current_database: str | None = None
    role_name: str | None = None
    calls: int | None = None
    mean_exec_time: float | None = None
    total_exec_time: float | None = None
    workload_impact_score: float | None = None
    contains_seq_scan: bool = False
    recommendation_status: str | None = None
    state: str = "new"
    first_seen_at: datetime
    last_seen_at: datetime

    model_config = {"from_attributes": True}


class IndexCandidateOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    query_fingerprint_id: uuid.UUID
    table_name: str
    schema_name: str = "public"
    index_method: str = "btree"
    columns: list[str]
    sort_directions: list[str] | None = None
    include_columns: list[str] | None = None
    predicate: str | None = None
    source_signals: list[str] = Field(default_factory=list)
    generation_rule: str | None = None
    estimated_size_bytes: int | None = None
    overlap_status: str = "NONE"
    overlap_detail: dict[str, Any] | None = None
    candidate_hash: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PlanSnapshotOut(BaseModel):
    id: uuid.UUID
    query_fingerprint_id: uuid.UUID
    captured_at: datetime
    plan_json: Any | None = None
    plan_hash: str | None = None
    root_node_type: str | None = None
    total_cost: float | None = None
    plan_rows: int | None = None
    planning_time: float | None = None
    analysis_mode: str = "GENERIC"
    plan_signals: dict[str, Any] | None = None

    model_config = {"from_attributes": True}

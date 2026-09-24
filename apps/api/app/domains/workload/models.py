"""Workload snapshot, query fingerprint, and query observation ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.domains.workspaces.models import Workspace
    from app.domains.plans.models import PlanSnapshot
    from app.domains.indexes.models import IndexCandidate


class WorkloadSnapshot(Base):
    __tablename__ = "workload_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    observation_window_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    observation_window_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    stats_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    query_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB)

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="snapshots")
    observations: Mapped[list["QueryObservation"]] = relationship(
        "QueryObservation", back_populates="snapshot", cascade="all, delete-orphan"
    )


class QueryFingerprint(Base):
    __tablename__ = "query_fingerprints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    workload_snapshot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workload_snapshots.id")
    )
    queryid: Mapped[Optional[int]] = mapped_column(BigInteger)
    normalized_sql: Mapped[str] = mapped_column(Text, nullable=False)
    current_database: Mapped[Optional[str]] = mapped_column(String(255))
    role_name: Mapped[Optional[str]] = mapped_column(String(255))
    calls: Mapped[Optional[int]] = mapped_column(BigInteger)
    mean_exec_time: Mapped[Optional[float]] = mapped_column(Float)
    total_exec_time: Mapped[Optional[float]] = mapped_column(Float)
    workload_impact_score: Mapped[Optional[float]] = mapped_column(Float, index=True)
    contains_seq_scan: Mapped[bool] = mapped_column(Boolean, default=False)
    recommendation_status: Mapped[Optional[str]] = mapped_column(String(50))
    state: Mapped[str] = mapped_column(String(50), nullable=False, default="new")
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="query_fingerprints")
    observations: Mapped[list["QueryObservation"]] = relationship(
        "QueryObservation", back_populates="query_fingerprint"
    )
    plan_snapshots: Mapped[list["PlanSnapshot"]] = relationship(
        "PlanSnapshot", back_populates="query_fingerprint"
    )
    candidates: Mapped[list["IndexCandidate"]] = relationship(
        "IndexCandidate", back_populates="query_fingerprint"
    )


class QueryObservation(Base):
    """Links a query fingerprint to a specific workload snapshot with stats."""

    __tablename__ = "query_observations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workload_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    query_fingerprint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("query_fingerprints.id", ondelete="CASCADE"), nullable=False
    )
    calls: Mapped[Optional[int]] = mapped_column(BigInteger)
    mean_exec_time: Mapped[Optional[float]] = mapped_column(Float)
    total_exec_time: Mapped[Optional[float]] = mapped_column(Float)
    rows: Mapped[Optional[int]] = mapped_column(BigInteger)
    shared_blks_hit: Mapped[Optional[int]] = mapped_column(BigInteger)
    shared_blks_read: Mapped[Optional[int]] = mapped_column(BigInteger)

    snapshot: Mapped["WorkloadSnapshot"] = relationship("WorkloadSnapshot", back_populates="observations")
    query_fingerprint: Mapped["QueryFingerprint"] = relationship(
        "QueryFingerprint", back_populates="observations"
    )

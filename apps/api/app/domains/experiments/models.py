"""Experiment, Recommendation, and MigrationArtifact ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.domains.indexes.models import IndexCandidate


class Experiment(Base):
    """One comparison between current and hypothetical planning conditions."""

    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("index_candidates.id", ondelete="CASCADE"), nullable=False
    )
    query_fingerprint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("query_fingerprints.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    hypopg_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    before_plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plan_snapshots.id")
    )
    after_plan_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    before_cost: Mapped[Optional[float]] = mapped_column(Float)
    after_cost: Mapped[Optional[float]] = mapped_column(Float)
    before_rows: Mapped[Optional[int]] = mapped_column(BigInteger)
    after_rows: Mapped[Optional[int]] = mapped_column(BigInteger)
    before_sort_nodes: Mapped[Optional[int]] = mapped_column(Integer)
    after_sort_nodes: Mapped[Optional[int]] = mapped_column(Integer)
    plan_changed: Mapped[Optional[bool]] = mapped_column(Boolean)
    storage_estimate_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    plan_diff: Mapped[Optional[dict]] = mapped_column(JSONB)
    error_code: Mapped[Optional[str]] = mapped_column(String(100))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    candidate: Mapped["IndexCandidate"] = relationship("IndexCandidate", back_populates="experiments")
    recommendation: Mapped[Optional["Recommendation"]] = relationship(
        "Recommendation", back_populates="experiment", uselist=False
    )


class Recommendation(Base):
    """Product conclusion for an index candidate after experimentation."""

    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("index_candidates.id", ondelete="CASCADE"), nullable=False
    )
    experiment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiments.id")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[Optional[float]] = mapped_column(Float)
    benefit_score: Mapped[Optional[float]] = mapped_column(Float)
    storage_penalty: Mapped[Optional[float]] = mapped_column(Float)
    write_penalty: Mapped[Optional[float]] = mapped_column(Float)
    overlap_penalty: Mapped[Optional[float]] = mapped_column(Float)
    evidence_quality: Mapped[Optional[str]] = mapped_column(String(20))
    reason_codes: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    explanation: Mapped[Optional[str]] = mapped_column(Text)
    ai_explanation: Mapped[Optional[str]] = mapped_column(Text)
    jev_review_path: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    experiment: Mapped[Optional["Experiment"]] = relationship("Experiment", back_populates="recommendation")
    migration_artifact: Mapped[Optional["MigrationArtifact"]] = relationship(
        "MigrationArtifact", back_populates="recommendation", uselist=False, cascade="all, delete-orphan"
    )


class MigrationArtifact(Base):
    """Generated SQL migration — display only, never auto-executed."""

    __tablename__ = "migration_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recommendation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recommendations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    rollback_sql_text: Mapped[Optional[str]] = mapped_column(Text)
    index_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    recommendation: Mapped["Recommendation"] = relationship(
        "Recommendation", back_populates="migration_artifact"
    )

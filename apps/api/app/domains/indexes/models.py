"""Index candidate and existing index inventory ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.domains.workload.models import QueryFingerprint
    from app.domains.experiments.models import Experiment


class IndexCandidate(Base):
    """A generated possible index for a query fingerprint."""

    __tablename__ = "index_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    query_fingerprint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("query_fingerprints.id", ondelete="CASCADE"), nullable=False
    )
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(255), nullable=False, default="public")
    index_method: Mapped[str] = mapped_column(String(50), nullable=False, default="btree")
    columns: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False)
    sort_directions: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String))
    include_columns: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String))
    predicate: Mapped[Optional[str]] = mapped_column(Text)
    source_signals: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    generation_rule: Mapped[Optional[str]] = mapped_column(String(100))
    estimated_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    overlap_status: Mapped[str] = mapped_column(String(50), nullable=False, default="NONE")
    overlap_detail: Mapped[Optional[dict]] = mapped_column(JSONB)
    candidate_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    query_fingerprint: Mapped["QueryFingerprint"] = relationship(
        "QueryFingerprint", back_populates="candidates"
    )
    experiments: Mapped[list["Experiment"]] = relationship(
        "Experiment", back_populates="candidate", cascade="all, delete-orphan"
    )


class IndexRecord(Base):
    """Existing physical index on the target database (refreshed per snapshot)."""

    __tablename__ = "index_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    schema_name: Mapped[str] = mapped_column(String(255), nullable=False, default="public")
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    index_name: Mapped[str] = mapped_column(String(255), nullable=False)
    index_method: Mapped[str] = mapped_column(String(50), nullable=False, default="btree")
    columns: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False)
    is_unique: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    index_definition: Mapped[Optional[str]] = mapped_column(Text)
    index_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    idx_scan: Mapped[Optional[int]] = mapped_column(BigInteger)
    idx_tup_read: Mapped[Optional[int]] = mapped_column(BigInteger)
    idx_tup_fetch: Mapped[Optional[int]] = mapped_column(BigInteger)
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

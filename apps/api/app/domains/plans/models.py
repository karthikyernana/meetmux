"""Plan snapshot ORM model."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.domains.workload.models import QueryFingerprint


class PlanSnapshot(Base):
    __tablename__ = "plan_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_fingerprint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("query_fingerprints.id", ondelete="CASCADE"), nullable=False
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    plan_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    plan_hash: Mapped[Optional[str]] = mapped_column(String(64))
    root_node_type: Mapped[Optional[str]] = mapped_column(String(100))
    total_cost: Mapped[Optional[float]] = mapped_column(Float)
    plan_rows: Mapped[Optional[int]] = mapped_column(Integer)
    planning_time: Mapped[Optional[float]] = mapped_column(Float)
    analysis_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="GENERIC")
    plan_signals: Mapped[Optional[dict]] = mapped_column(JSONB)

    query_fingerprint: Mapped["QueryFingerprint"] = relationship(
        "QueryFingerprint", back_populates="plan_snapshots"
    )

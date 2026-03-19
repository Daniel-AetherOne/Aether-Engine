from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Integer, JSON, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.schema import UniqueConstraint
from sqlalchemy.sql import func

from app.db import Base


class LeadTrainingRecord(Base):
    __tablename__ = "lead_training_records"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "lead_id",
            name="uq_lead_training_tenant_lead",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    lead_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("leads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    capture_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="v1",
    )
    outcome: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    outcome_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    intake_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    photo_refs: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    estimate_input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    estimate_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    pricing_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )


# app/models/lead.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # multi-tenant
    tenant_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)

    # vertical
    vertical: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )

    # contact
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # project/meta (freeform)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # status/meta
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="NEW",  # db-default (beter dan default=)
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # artifacts/payloads (JSON als string voor MVP)
    intake_payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estimate_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estimate_html_key: Mapped[Optional[str]] = mapped_column(
        String(1024), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # files relatie
    files: Mapped[List["LeadFile"]] = relationship(
        "LeadFile",
        back_populates="lead",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Lead id={self.id} tenant={self.tenant_id} name={self.name!r}>"


class LeadFile(Base):
    __tablename__ = "lead_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # canonieke key (na finalize_move), bv. "leads/{lead_id}/file.jpg"
    s3_key: Mapped[str] = mapped_column(String(1024), index=True, nullable=False)

    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)

    lead: Mapped["Lead"] = relationship("Lead", back_populates="files")

    def __repr__(self) -> str:
        return f"<LeadFile lead_id={self.lead_id} key={self.s3_key!r}>"

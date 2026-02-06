# app/models/tenant_settings.py
from __future__ import annotations
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, Text
from app.db import Base  # gebruik de Base uit jouw databaseconfig


class TenantSettings(Base):
    __tablename__ = "tenant_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(
        String(100), index=True, unique=True, nullable=False
    )

    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    logo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # HubSpot integratievelden
    hubspot_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pipeline: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    stage: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Branding
    primary_color: Mapped[str] = mapped_column(String(20), default="#2563eb")
    secondary_color: Mapped[str] = mapped_column(String(20), default="#64748b")

    def __repr__(self) -> str:
        return f"<TenantSettings tenant_id={self.tenant_id!r} company_name={self.company_name!r}>"

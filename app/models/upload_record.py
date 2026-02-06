from __future__ import annotations

import enum

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum as SAEnum,
    Index,
    Integer,
    JSON,
    String,
    func,
)

from app.db import Base


class UploadStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    rejected = "rejected"


class UploadRecord(Base):
    __tablename__ = "upload_records"

    id = Column(Integer, primary_key=True)

    # Multi-tenant safety: always store tenant_id for correct scoping
    tenant_id = Column(Integer, nullable=False, index=True)

    # Link to lead
    lead_id = Column(Integer, nullable=False, index=True)

    # Storage key (S3 key / blob key)
    object_key = Column(String(1024), nullable=False, unique=True, index=True)

    # File metadata
    size = Column(BigInteger, nullable=False)
    mime = Column(String(255), nullable=False)

    etag = Column(String(128), nullable=True)
    s3_metadata = Column(JSON, nullable=True)

    status = Column(
        SAEnum(UploadStatus, name="upload_status"),
        nullable=False,
        default=UploadStatus.uploaded,
        server_default=UploadStatus.uploaded.value,
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        # Fast lookups: "all uploads for this lead in this tenant"
        Index("ix_upload_records_tenant_lead", "tenant_id", "lead_id"),
        # Optional but useful: queries like "all pending/processing for tenant"
        Index("ix_upload_records_tenant_status", "tenant_id", "status"),
    )

    @property
    def is_image(self) -> bool:
        return bool(self.mime) and self.mime.startswith("image/")

    @property
    def is_ready(self) -> bool:
        # "uploaded" means the object exists and is ready for downstream steps
        return self.status == UploadStatus.uploaded

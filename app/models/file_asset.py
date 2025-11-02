# app/models/file_asset.py
from sqlalchemy import Column, String, Integer, DateTime, Enum, JSON, Boolean
from sqlalchemy.sql import func
import enum
from app.db import Base

class ScanStatus(str, enum.Enum):
    pending_upload = "pending_upload"
    uploaded = "uploaded"
    queued_scan = "queued_scan"
    clean = "clean"
    infected = "infected"
    failed = "failed"

class FileAsset(Base):
    __tablename__ = "file_assets"
    id = Column(String, primary_key=True)            # ULID/UUID
    filename = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    s3_key = Column(String, nullable=False, unique=True)
    checksum_sha256 = Column(String, nullable=True)  # hex of base64; we bewaren beide vormen evt
    etag = Column(String, nullable=True)
    content_disposition = Column(String, nullable=True)  # "inline" of 'attachment; filename="..."'
    scan_status = Column(Enum(ScanStatus), default=ScanStatus.pending_upload, nullable=False)
    meta = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

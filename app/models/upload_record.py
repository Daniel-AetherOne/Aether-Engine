from sqlalchemy import Column, Integer, String, Enum, BigInteger, JSON, DateTime, func
import enum
from app.db import Base

class UploadStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    rejected = "rejected"

class UploadRecord(Base):
    __tablename__ = "upload_records"

    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, index=True, nullable=False)
    object_key = Column(String(1024), nullable=False, unique=True, index=True)
    size = Column(BigInteger, nullable=False)
    mime = Column(String(255), nullable=False)
    etag = Column(String(128), nullable=True)
    s3_metadata = Column(JSON, nullable=True)
    status = Column(Enum(UploadStatus), nullable=False, default=UploadStatus.uploaded)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

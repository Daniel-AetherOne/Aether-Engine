from datetime import datetime
from uuid import uuid4
from sqlalchemy import Column, String, DateTime, Text
from app.db import Base

class UploadStatus(Base):
    __tablename__ = "upload_status"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String, nullable=False)
    object_key = Column(String, nullable=False, index=True)
    status = Column(String, default="pending")  # pending | verified | failed
    verified_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)

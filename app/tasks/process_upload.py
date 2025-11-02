# app/tasks/process_upload.py
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.models.upload_record import UploadRecord, UploadStatus

def process_upload(upload_id: int):
    db: Session = SessionLocal()
    try:
        rec = db.query(UploadRecord).get(upload_id)
        if not rec:
            return
        # 1) Virus scan (e.g., ClamAV via Lambda or local daemon)
        # 2) Thumbnails for images/PDF
        # 3) OCR to text (store next to record or in a separate table)
        rec.status = UploadStatus.processing
        db.add(rec)
        db.commit()
    except Exception:
        db.rollback()
        # (optional) mark as rejected or write to DLQ
    finally:
        db.close()

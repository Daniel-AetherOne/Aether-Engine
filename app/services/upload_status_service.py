# app/services/upload_status_service.py
import asyncio
import httpx
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.upload_status import UploadStatus
from app.core.settings import settings  # of vervang door je eigen configmodule


async def verify_object(session: Session, status: UploadStatus):
    s3_url = f"{settings.S3_BASE_URL}/{status.object_key}"

    try:
        async with httpx.AsyncClient() as client:
            r = await client.head(s3_url, timeout=5.0)
            if r.status_code == 200:
                status.status = "verified"
                status.verified_at = datetime.utcnow()
            else:
                status.status = "failed"
                status.error = f"HEAD {r.status_code}"
    except Exception as e:
        status.status = "failed"
        status.error = str(e)

    session.add(status)
    session.commit()


async def background_verifier(db_factory):
    """Background task that periodically checks pending uploads"""
    while True:
        db = db_factory()
        pending = db.query(UploadStatus).filter(UploadStatus.status == "pending").all()
        if pending:
            print(f"Verifying {len(pending)} pending uploads...")
        for item in pending:
            await verify_object(db, item)
        db.close()
        await asyncio.sleep(30)

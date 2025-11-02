# app/api/routes/uploads.py
from __future__ import annotations

from fastapi import APIRouter, Depends, BackgroundTasks, Request, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.uploads import VerifyUploadIn, UploadRecordOut
from app.services.upload_verification import verify_and_persist
from app.models.upload_record import UploadRecord

from time import perf_counter
from app.core.logging_config import logger
from app.observability.metrics import verify_counter, latency_hist

router = APIRouter(prefix="/uploads", tags=["uploads"])


def _start_processing_background(upload_id: int) -> None:
    """
    Vervang dit door Celery/RQ als je een echte worker hebt.
    """
    from app.tasks.process_upload import process_upload  # lokale/background fn
    process_upload(upload_id)


@router.post("/verify", response_model=UploadRecordOut)
def verify_upload(
    request: Request,
    payload: VerifyUploadIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    # user: User = Depends(current_user),  # indien auth/logging op user nodig is
) -> UploadRecordOut:
    t0 = perf_counter()
    trace_id = getattr(request.state, "trace_id", None)

    try:
        # Verifieer upload en sla op in DB
        record: UploadRecord = verify_and_persist(db, payload)

        # Background processing (thumbnail/ocr/scan/etc.)
        background.add_task(_start_processing_background, record.id)

        # ---- logging (success) ----
        logger.info(
            "verify_ok",
            extra={
                "extra": {
                    "event": "verify",
                    "result": "success",
                    "trace_id": trace_id,
                    "lead_id": record.lead_id,
                    "object_key": record.object_key,
                    "etag": record.etag,
                    "content_length": payload.content_length,
                    "mime": record.mime,
                    "size": record.size,
                    # "user_id": getattr(user, "id", None) if 'user' gebruikt wordt
                }
            },
        )

        # ---- metrics (success) ----
        verify_counter.labels(result="success").inc()

        return UploadRecordOut(
            id=record.id,
            lead_id=record.lead_id,
            object_key=record.object_key,
            size=record.size,
            mime=record.mime,
            etag=record.etag,
            status=record.status.value,
            metadata=record.metadata,
        )

    except HTTPException:
        # Doorvertaalde, ‘gecontroleerde’ fouten tellen als error
        verify_counter.labels(result="error").inc()
        logger.info(
            "verify_error_http",
            extra={
                "extra": {
                    "event": "verify",
                    "result": "error",
                    "trace_id": trace_id,
                    "lead_id": getattr(payload, "lead_id", None),
                    "object_key": getattr(payload, "object_key", None),
                    "etag": getattr(payload, "etag", None),
                    "content_length": getattr(payload, "content_length", None),
                }
            },
        )
        raise

    except Exception as e:
        # Onverwachte fouten
        verify_counter.labels(result="error").inc()
        logger.info(
            "verify_error",
            extra={
                "extra": {
                    "event": "verify",
                    "result": "error",
                    "trace_id": trace_id,
                    "lead_id": getattr(payload, "lead_id", None),
                    "object_key": getattr(payload, "object_key", None),
                    "etag": getattr(payload, "etag", None),
                    "content_length": getattr(payload, "content_length", None),
                    "error": str(e),
                }
            },
        )
        raise

    finally:
        latency_hist.labels(route="/uploads/verify").observe(perf_counter() - t0)

from app.core.settings import settings
from celery.utils.log import get_task_logger
import os
from typing import Dict, Any, List
import uuid
from datetime import datetime

# Celery configuratie
celery_app = Celery(
    "levelai",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

# Celery configuratie
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Amsterdam",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minuten
    task_soft_time_limit=25 * 60,  # 25 minuten
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Logger
logger = get_task_logger(__name__)

# Job status tracking
job_statuses = {}


def get_job_status(job_id: str) -> Dict[str, Any]:
    """Haal job status op"""
    return job_statuses.get(job_id, {"status": "not_found"})


def update_job_status(job_id: str, status: str, result: Any = None, error: str = None):
    """Update job status"""
    job_statuses[job_id] = {
        "status": status,
        "result": result,
        "error": error,
        "updated_at": datetime.now().isoformat(),
    }
    logger.info(f"Job {job_id} status updated to {status}")


def create_job() -> str:
    """Maak nieuwe job aan"""
    job_id = str(uuid.uuid4())
    update_job_status(job_id, "pending")
    logger.info(f"Created new job: {job_id}")
    return job_id

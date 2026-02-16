import time
import threading
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.job import Job


POLL_INTERVAL = 5  # seconden


def process_job(job: Job, db: Session):
    """
    Simuleert verwerking.
    Later vervang je dit met echte AI / pricing / PDF / etc.
    """

    job.status = "IN_PROGRESS"
    db.commit()

    time.sleep(2)  # simulate work

    job.status = "DONE"
    db.commit()


def worker_loop():
    while True:
        db: Session = SessionLocal()

        try:
            job = (
                db.query(Job)
                .filter(Job.status == "NEW")
                .order_by(Job.created_at.asc())
                .first()
            )

            if job:
                process_job(job, db)

        finally:
            db.close()

        time.sleep(POLL_INTERVAL)


def start_worker():
    thread = threading.Thread(target=worker_loop, daemon=True)
    thread.start()

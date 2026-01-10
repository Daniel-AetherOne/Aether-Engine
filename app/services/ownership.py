# app/services/ownership.py
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.core.settings import settings


def assert_lead_belongs_to_user(db: Session, lead_id: int, user_id: int) -> None:
    """
    Ownership enforcement.

    Hardening:
    - Dev: allow to keep building.
    - Prod: explicitly blocked until real ownership (user/tenant mapping) exists.
    """
    if settings.ENABLE_DEV_ROUTES:
        return

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Ownership check not implemented",
    )

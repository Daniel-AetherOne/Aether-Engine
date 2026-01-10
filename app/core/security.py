# app/core/security.py
from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from app.core.settings import settings


class User(BaseModel):
    id: int
    email: str


def get_current_user():
    if not settings.ENABLE_DEV_ROUTES:
        raise HTTPException(status_code=401, detail="Auth not configured")
    return User(id=1, email="dev@example.com")

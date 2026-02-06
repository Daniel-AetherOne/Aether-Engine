from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth.jwt import decode_token
from app.models.user import User

bearer = HTTPBearer(auto_error=False)


def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> User | None:
    token = request.cookies.get("access_token")
    if not token and creds and creds.credentials:
        token = creds.credentials
    if not token:
        return None

    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return None
    except Exception:
        return None

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        return None
    return user

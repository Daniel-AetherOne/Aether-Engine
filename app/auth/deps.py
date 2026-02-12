from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth.jwt import decode_token
from app.models.user import User

security = HTTPBearer(auto_error=False)  # <- belangrijk: niet auto-error


def _extract_token(
    request: Request, creds: HTTPAuthorizationCredentials | None
) -> str | None:
    # 1) cookie
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token

    # 2) Authorization header
    if creds and creds.credentials:
        return creds.credentials

    return None


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = _extract_token(request, creds)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user


def require_user_html(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = _extract_token(request, creds)
    if not token:
        path = request.url.path
        qs = request.url.query
        next_url = path + (("?" + qs) if qs else "")
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Not authenticated",
            headers={"Location": f"/auth/login?next={next_url}"},
        )

    try:
        payload = decode_token(token)
    except Exception:
        path = request.url.path
        qs = request.url.query
        next_url = path + (("?" + qs) if qs else "")
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Invalid token",
            headers={"Location": f"/auth/login?next={next_url}"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user

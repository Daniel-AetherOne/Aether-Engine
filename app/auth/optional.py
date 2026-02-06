from fastapi import Depends, Request
from sqlalchemy.orm import Session
from app.db import get_db
from app.auth.deps import security, _extract_token  # hergebruik als je die helper hebt
from app.auth.jwt import decode_token
from app.models.user import User

def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
    creds = Depends(security),
) -> User | None:
    token = _extract_token(request, creds)
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

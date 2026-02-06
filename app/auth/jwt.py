from datetime import datetime, timedelta, timezone
import jwt
from app.core.settings import settings


def create_access_token(*, user_id: str, tenant_id: str, email: str) -> str:
    now = datetime.now(timezone.utc)
    exp_hours = int(getattr(settings, "JWT_EXP_HOURS", 24))

    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=exp_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])

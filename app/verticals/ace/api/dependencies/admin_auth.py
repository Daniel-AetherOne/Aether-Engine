import os
import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.verticals.ace.domain.auth import AdminIdentity

security = HTTPBasic(realm="Admin")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


def require_admin(
    credentials: HTTPBasicCredentials = Depends(security),
) -> AdminIdentity:
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        raise RuntimeError("ADMIN_USERNAME/ADMIN_PASSWORD not configured")

    ok_user = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    ok_pass = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)

    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return AdminIdentity(username=credentials.username)

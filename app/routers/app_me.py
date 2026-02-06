# app/routers/app_me.py
from fastapi import APIRouter, Depends
from app.auth.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/app", tags=["app"])


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"user_id": user.id, "email": user.email, "tenant_id": user.tenant_id}

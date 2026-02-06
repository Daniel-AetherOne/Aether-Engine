from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth.deps import get_current_user
from app.models.user import User
from app.models.lead import Lead

router = APIRouter(prefix="/app", tags=["app"])

@router.get("/leads")
def list_leads(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    leads = (
        db.query(Lead)
        .filter(Lead.tenant_id == user.tenant_id)
        .order_by(Lead.id.desc())
        .limit(200)
        .all()
    )
    return [{"id": l.id, "status": l.status, "email": l.email, "name": l.name} for l in leads]

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.tenant import Tenant
from app.verticals.registry import get as get_vertical

router = APIRouter(tags=["public-intake"])


@router.get("/t/{tenant_id}/intake")
def public_intake_page(
    request: Request,
    tenant_id: str,
    db: Session = Depends(get_db),
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    v = get_vertical("paintly")

    return v.render_intake_form(
        request=request,
        lead_id="",
        tenant_id=tenant.id,
        extra_context={"tenant": tenant},
    )

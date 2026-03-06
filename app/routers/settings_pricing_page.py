from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Tenant

router = APIRouter(tags=["settings-pricing-page"])


def get_current_tenant_id() -> str:
    return "dev-tenant"


@router.get("/settings/pricing", response_class=HTMLResponse)
def pricing_settings_page(
    request: Request,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    pricing = tenant.pricing_json or {}
    value = pricing.get("walls_rate_eur_per_sqm")

    try:
        walls_rate = float(value) if value is not None else None
    except (TypeError, ValueError):
        walls_rate = None

    saved = request.query_params.get("saved") == "1"

    return request.app.state.templates.TemplateResponse(
        "settings_pricing.html",
        {
            "request": request,
            "walls_rate_eur_per_sqm": walls_rate,
            "saved": saved,
        },
    )


@router.post("/settings/pricing")
def pricing_settings_save(
    request: Request,
    walls_rate_eur_per_sqm: float = Form(...),
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
):
    if walls_rate_eur_per_sqm < 5 or walls_rate_eur_per_sqm > 100:
        raise HTTPException(
            status_code=400,
            detail="walls_rate_eur_per_sqm must be between 5 and 100",
        )

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    existing = tenant.pricing_json or {}
    tenant.pricing_json = {
        **existing,
        "walls_rate_eur_per_sqm": float(walls_rate_eur_per_sqm),
    }

    print("SETTINGS_SAVE DEBUG BEFORE COMMIT:", tenant.id, tenant.pricing_json)

    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    print("SETTINGS_SAVE DEBUG AFTER REFRESH:", tenant.id, tenant.pricing_json)

    return RedirectResponse(url="/settings/pricing?saved=1", status_code=303)

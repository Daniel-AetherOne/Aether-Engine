# app/routers/intake.py
from __future__ import annotations

import logging
import uuid
import secrets

from fastapi import APIRouter, Request, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.verticals.registry import get as get_vertical
from app.verticals.paintly.eu_config import resolve_eu_config  # ✅ ADD

from app.auth.optional_user import get_optional_user
from app.models.user import User
from app.models.tenant import Tenant
from app.models.lead import Lead as LeadModel

router = APIRouter(prefix="/intake", tags=["intake"])
logger = logging.getLogger(__name__)

DEFAULT_VERTICAL = "paintly"


def _normalize_vertical_id(vertical: str) -> str:
    """
    Accept slugs like:
      - painters-us
      - painters_us
      - Painters-US
    Normalize to registry key: painters_us
    """
    return (vertical or "").strip().lower().replace("-", "_")


def _wants_json(request: Request) -> bool:
    """
    JSON when:
    - ?format=json
    - Accept: application/json (Swagger does this)
    """
    fmt = (request.query_params.get("format") or "").lower().strip()
    if fmt == "json":
        return True
    accept = (request.headers.get("accept") or "").lower()
    return "application/json" in accept


def _status_url(lead_id: str) -> str:
    """
    Bepaalt de redirect na intake submit.

    Voor de Paintly-demo sturen we na intake altijd eerst naar de
    AI-gestuurde statuspagina, zodat de klant de analyse/progress
    ziet voordat de offerte klaar is.

    Let op: voor JSON flows wordt deze URL alleen als 'next.status' meegegeven.
    """
    return f"/quotes/{lead_id}/status?autostart=1&demo=1"


def _get_vertical_or_404(vertical: str):
    vertical_id = _normalize_vertical_id(vertical)
    try:
        return get_vertical(vertical_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# -------------------------
# EU config (for country dropdown)
# Put this BEFORE /{vertical} so it won't be captured as "vertical"
# -------------------------
@router.get("/eu/config")
def eu_config(country: str = Query("NL", min_length=2, max_length=2)):
    country = (country or "NL").strip().upper()
    return resolve_eu_config(country)


async def _create_lead_impl(
    request: Request,
    vertical: str,
    db: Session,
    user: User | None,
):
    v = _get_vertical_or_404(vertical)

    form = await request.form()
    form_tenant_id = (form.get("tenant_id") or "").strip()

    if form_tenant_id:
        tenant_id = form_tenant_id
    elif user and user.tenant_id:
        tenant_id = str(user.tenant_id)
    else:
        tenant_id = "dev-tenant"

    if hasattr(v, "upsert_lead_from_form"):
        result = await v.upsert_lead_from_form(
            request,
            db,
            tenant_id=tenant_id,
        )
    else:
        result = await v.create_lead_from_form(
            request,
            db,
            tenant_id=tenant_id,
        )

    logger.info(
        "INTAKE created lead=%s vertical=%s tenant=%s",
        result.lead_id,
        result.vertical,
        result.tenant_id,
    )

    # Bepaal redirect:
    # DEMO-MODUS:
    # - Na intake altijd eerst naar de AI-gestuurde statuspagina,
    #   zodat de klant de analyse/progress ziet voordat de uiteindelijke
    #   offerte of NEEDS_REVIEW-status zichtbaar wordt.
    status_url = _status_url(result.lead_id)

    if _wants_json(request):
        return JSONResponse(
            {
                "lead_id": result.lead_id,
                "tenant_id": result.tenant_id,
                "files": result.files,
                "vertical": result.vertical,
                "next": {
                    "status": status_url,
                    "publish_estimate": f"/quotes/publish/{result.lead_id}",
                    "json": f"/quotes/{result.lead_id}/json",
                    "html": f"/quotes/{result.lead_id}/html",
                },
            }
        )

    return RedirectResponse(url=status_url, status_code=303)


# -------------------------
# Backward compatible routes
# Keep this BEFORE /{vertical} too, otherwise it gets treated as vertical.
# -------------------------
@router.get("/painters-us", include_in_schema=False)
def intake_painters_us_redirect():
    # ✅ keep old link working, but always use paintly now
    return RedirectResponse(url="/intake/paintly", status_code=302)


@router.get("/t/{tenant_slug}", response_class=HTMLResponse)
def intake_by_tenant_slug(
    request: Request,
    tenant_slug: str,
    db: Session = Depends(get_db),
):
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    v = _get_vertical_or_404(DEFAULT_VERTICAL)

    return v.render_intake_form(
        request,
        lead_id=str(uuid.uuid4()),
        tenant_id=str(tenant.id),
        submit_url=f"/intake/t/{tenant_slug}/lead",
    )


@router.post("/t/{tenant_slug}/lead")
async def create_lead_by_tenant_slug(
    request: Request,
    tenant_slug: str,
    db: Session = Depends(get_db),
):
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        v = _get_vertical_or_404(DEFAULT_VERTICAL)

        if hasattr(v, "upsert_lead_from_form"):
            result = await v.upsert_lead_from_form(
                request,
                db,
                tenant_id=str(tenant.id),
            )
        else:
            result = await v.create_lead_from_form(
                request,
                db,
                tenant_id=str(tenant.id),
            )

        logger.info(
            "INTAKE created lead=%s via tenant_slug=%s tenant=%s",
            result.lead_id,
            tenant_slug,
            result.tenant_id,
        )

        # Publieke tenant-intake: stuur klant naar publieke conceptofferte (Paintly-specifiek)
        status_url = _status_url(result.lead_id)
        try:
            lead_id_int = int(result.lead_id)
            lead = db.query(LeadModel).filter(LeadModel.id == lead_id_int).first()
        except Exception:
            lead = None

        if lead is not None and (getattr(lead, "vertical", "") or "").lower() == "paintly":
            # Zorg dat er een public_token is voor publieke offerte-url
            if not getattr(lead, "public_token", None):
                lead.public_token = secrets.token_hex(16)
                db.add(lead)
                db.commit()
                db.refresh(lead)

            public_token = getattr(lead, "public_token", None)
            if public_token:
                status_url = f"/e/{public_token}"

        if _wants_json(request):
            return JSONResponse(
                {
                    "lead_id": result.lead_id,
                    "tenant_id": result.tenant_id,
                    "files": result.files,
                    "vertical": result.vertical,
                    "next": {
                        "status": status_url,
                        "publish_estimate": f"/quotes/publish/{result.lead_id}",
                        "json": f"/quotes/{result.lead_id}/json",
                        "html": f"/quotes/{result.lead_id}/html",
                    },
                }
            )

        return RedirectResponse(url=status_url, status_code=303)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_lead_by_tenant_slug crashed")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------
# New dynamic routes
# -------------------------
@router.get("/{vertical}", response_class=HTMLResponse)
def intake_by_vertical(
    request: Request,
    vertical: str,
    user: User | None = Depends(get_optional_user),
):
    v = _get_vertical_or_404(vertical)

    tenant_id = user.tenant_id if user else "public"

    return v.render_intake_form(
        request,
        lead_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        submit_url=f"/intake/{vertical}/lead",
    )


@router.post("/{vertical}/lead")
async def create_lead_by_vertical(
    request: Request,
    vertical: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    try:
        return await _create_lead_impl(request, vertical, db, user)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_lead crashed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/lead")
async def create_lead_legacy(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    try:
        return await _create_lead_impl(request, DEFAULT_VERTICAL, db, user)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_lead crashed")
        raise HTTPException(status_code=500, detail=str(e))

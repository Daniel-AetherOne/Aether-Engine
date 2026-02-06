# app/routers/intake.py
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.verticals.registry import get as get_vertical

from app.auth.optional_user import get_optional_user
from app.models.user import User

router = APIRouter(prefix="/intake", tags=["intake"])
logger = logging.getLogger(__name__)

DEFAULT_VERTICAL = "painters_us"


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
    return f"/quotes/{lead_id}/status?autostart=1"


def _get_vertical_or_404(vertical: str):
    vertical_id = _normalize_vertical_id(vertical)
    try:
        return get_vertical(vertical_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


async def _create_lead_impl(
    request: Request,
    vertical: str,
    db: Session,
    user: User | None,
):
    v = _get_vertical_or_404(vertical)

    tenant_id = user.tenant_id if user else "public"

    # BELANGRIJK: tenant_id meegeven aan adapter
    result = await v.create_lead_from_form(request, db, tenant_id=tenant_id)

    logger.info(
        "INTAKE created lead=%s vertical=%s tenant=%s",
        result.lead_id,
        result.vertical,
        result.tenant_id,
    )

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
# New dynamic routes
# -------------------------
@router.get("/{vertical}", response_class=HTMLResponse)
def intake_by_vertical(
    request: Request,
    vertical: str,
    user: User | None = Depends(get_optional_user),
):
    v = _get_vertical_or_404(vertical)

    # optioneel: tenant_id meegeven aan template (niet security-relevant)
    tenant_id = user.tenant_id if user else "public"

    return v.render_intake_form(
        request,
        lead_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
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


# -------------------------
# Backward compatible routes
# -------------------------
@router.get("/painters-us", response_class=HTMLResponse)
def intake_painters_us(
    request: Request,
    user: User | None = Depends(get_optional_user),
):
    v = get_vertical(DEFAULT_VERTICAL)

    tenant_id = user.tenant_id if user else "public"

    return v.render_intake_form(
        request,
        lead_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
    )


@router.post("/lead")
async def create_lead_legacy(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_user),
):
    # legacy: default vertical, maar wel tenant-aware + dependencies OK
    try:
        return await _create_lead_impl(request, DEFAULT_VERTICAL, db, user)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_lead crashed")
        raise HTTPException(status_code=500, detail=str(e))

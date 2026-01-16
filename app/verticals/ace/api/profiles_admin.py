from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.verticals.ace.api.dependencies.admin_auth import require_admin
from app.verticals.ace.domain.auth import AdminIdentity
from app.verticals.ace.audit_log import AuditLog, audit_db_path

from app.verticals.ace.profiles_store import (
    MAX_PROFILES,
    load_profiles,
    upsert_profile,
    delete_profile,
)

router = APIRouter(prefix="/admin/profiles", tags=["profiles-admin"])
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)

audit = AuditLog(audit_db_path())


@router.get("", response_class=HTMLResponse)
def profiles_page(
    request: Request,
    admin: AdminIdentity = Depends(require_admin),
):
    profiles = load_profiles()
    return templates.TemplateResponse(
        "admin_profiles.html",
        {
            "request": request,
            "profiles": profiles,
            "max_profiles": MAX_PROFILES,
        },
    )


@router.post("/upsert")
def profiles_upsert(
    profileCode: str = Form(...),
    standaardKortingPct: float = Form(...),
    maxExtraKortingPct: float = Form(...),
    beschrijving: str = Form(""),
    active: bool = Form(False),
    admin: AdminIdentity = Depends(require_admin),
):
    try:
        _, before, after = upsert_profile(
            profileCode=profileCode,
            standaardKortingPct=standaardKortingPct,
            maxExtraKortingPct=maxExtraKortingPct,
            beschrijving=beschrijving,
            active=active,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)})

    audit.append(
        event_id=f"profile_upsert:{after.profileCode}:{uuid.uuid4().hex}",
        event_type="DISCOUNT_PROFILE_UPDATED" if before else "DISCOUNT_PROFILE_CREATED",
        actor=admin,
        meta={
            "profileCode": after.profileCode,
            "before": (vars(before) if before else None),
            "after": vars(after),
        },
    )
    return RedirectResponse(url="/admin/profiles", status_code=303)


@router.post("/delete")
def profiles_delete(
    profileCode: str = Form(...),
    admin: AdminIdentity = Depends(require_admin),
):
    _, before = delete_profile(profileCode)
    if before is None:
        raise HTTPException(status_code=404, detail={"message": "Profile not found"})

    audit.append(
        event_id=f"profile_deleted:{profileCode}:{uuid.uuid4().hex}",
        event_type="DISCOUNT_PROFILE_DELETED",
        actor=admin,
        meta={"profileCode": profileCode, "before": vars(before)},
    )
    return RedirectResponse(url="/admin/profiles", status_code=303)

from pathlib import Path
from uuid import uuid4
import re
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.jwt import create_access_token
from app.auth.passwords import hash_password, verify_password
from app.db import get_db
from app.models.tenant import Tenant
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

TEMPLATES_DIR = (
    Path(__file__).resolve().parents[1] / "verticals" / "paintly" / "templates"
)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def slugify(value: str) -> str:
    value = (value or "").lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-")


# ---------- HTML pages ----------


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/app/leads"):
    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request, "next": next},
    )


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(
        "auth/register.html",
        {"request": request},
    )


# ---------- Form POST endpoints (cookie-setting) ----------


@router.post("/login")
def login_form(
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/app/leads"),
    db: Session = Depends(get_db),
):
    logger.info("AUTH_LOGIN_FORM_HIT email=%s", email)
    email_norm = email.lower().strip()
    user = db.query(User).filter(User.email == email_norm).first()

    if not user or not verify_password(password, user.password_hash):
        logger.warning("AUTH_LOGIN_INVALID_CREDENTIALS email=%s", email_norm)
        return RedirectResponse(url=f"/auth/login?next={next}", status_code=302)

    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
    )

    if not next.startswith("/"):
        next = "/app/leads"

    logger.info("AUTH_LOGIN_SUCCESS user_id=%s tenant_id=%s", user.id, user.tenant_id)
    resp = RedirectResponse(url=next, status_code=302)
    resp.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,  # True in prod
        max_age=60 * 60 * 24,
        path="/",
    )
    return resp


@router.post("/register")
def register_form(
    company_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(None),
    walls_rate_eur_per_sqm: float = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    logger.info("AUTH_REGISTER_FORM_HIT email=%s company_name=%s", email, company_name)
    company_name_clean = company_name.strip()
    email_norm = email.lower().strip()
    phone_clean = phone.strip() if phone else None

    existing = db.query(User).filter(User.email == email_norm).first()
    if existing:
        logger.warning("AUTH_REGISTER_EMAIL_EXISTS email=%s", email_norm)
        return RedirectResponse(url="/auth/login", status_code=302)

    base_slug = slugify(company_name_clean) or "tenant"
    slug = base_slug
    counter = 2

    while db.query(Tenant).filter(Tenant.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    trial_start = datetime.now(timezone.utc)
    trial_end = trial_start + timedelta(days=14)

    tenant = Tenant(
        id=str(uuid4()),
        name=company_name_clean,
        company_name=company_name_clean,
        email=email_norm,
        phone=phone_clean,
        slug=slug,
        plan_code="pro_199",
        subscription_status="trialing",
        trial_ends_at=trial_end,
        pricing_json={
            "walls_rate_eur_per_sqm": float(walls_rate_eur_per_sqm),
        },
    )

    user = User(
        id=str(uuid4()),
        tenant_id=tenant.id,
        email=email_norm,
        password_hash=hash_password(password[:72]),
        is_active=True,
    )

    db.add(tenant)
    db.add(user)
    db.commit()
    db.refresh(tenant)
    db.refresh(user)

    token = create_access_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        email=user.email,
    )

    resp = RedirectResponse(url="/app/leads", status_code=303)
    resp.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,  # True in prod
        max_age=60 * 60 * 24,
        path="/",
    )
    logger.info("AUTH_REGISTER_SUCCESS user_id=%s tenant_id=%s", user.id, user.tenant_id)
    return resp


@router.post("/logout")
def logout():
    resp = RedirectResponse(url="/auth/login", status_code=302)
    resp.delete_cookie("access_token", path="/")
    return resp

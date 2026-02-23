from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from uuid import uuid4

from app.db import get_db
from app.models.user import User
from app.models.tenant import Tenant
from app.auth.jwt import create_access_token
from app.auth.passwords import hash_password, verify_password
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

router = APIRouter(prefix="/auth", tags=["auth"])

templates = Jinja2Templates(directory="app/verticals/paintly/templates")


TEMPLATES_DIR = (
    Path(__file__).resolve().parents[1] / "verticals" / "paintly" / "templates"
)
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

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


# ---------- JSON API endpoints (blijven werken) ----------
# (als je ze al had: laat staan)

# ---------- Form POST endpoints (cookie-setting) ----------


@router.post("/login")
def login_form(
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/app/leads"),
    db: Session = Depends(get_db),
):
    email_norm = email.lower().strip()
    user = db.query(User).filter(User.email == email_norm).first()
    if not user or not verify_password(password, user.password_hash):
        return RedirectResponse(url=f"/auth/login?next={next}", status_code=302)

    token = create_access_token(
        user_id=user.id, tenant_id=user.tenant_id, email=user.email
    )

    # open-redirect bescherming (alleen relative paths toestaan)
    if not next.startswith("/"):
        next = "/app/leads"

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
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email_norm = email.lower().strip()
    existing = db.query(User).filter(User.email == email_norm).first()
    if existing:
        return RedirectResponse(url="/auth/login", status_code=302)

    tenant = Tenant(id=str(uuid4()), name=company_name.strip())
    user = User(
        id=str(uuid4()),
        tenant_id=tenant.id,
        email=email_norm,
        password_hash=hash_password(password),
        is_active=True,
    )

    db.add(tenant)
    db.add(user)
    db.commit()

    token = create_access_token(
        user_id=user.id, tenant_id=user.tenant_id, email=user.email
    )

    resp = RedirectResponse(url="/app/leads", status_code=302)
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


@router.post("/logout")
def logout():
    resp = RedirectResponse(url="/auth/login", status_code=302)
    resp.delete_cookie("access_token", path="/")
    return resp

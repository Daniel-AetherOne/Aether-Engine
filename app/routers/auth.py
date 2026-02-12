from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from uuid import uuid4

from app.db import get_db
from app.models.user import User
from app.models.tenant import Tenant
from app.auth.jwt import create_access_token
from app.auth.passwords import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------- HTML pages ----------


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/app/leads"):
    return HTMLResponse(
        f"""
        <!doctype html>
        <html><head><meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Login</title>
        <style>
          body{{font-family:system-ui;margin:40px;max-width:420px}}
          input{{width:100%;padding:10px;margin:8px 0;border:1px solid #ddd;border-radius:10px}}
          button{{width:100%;padding:10px;border-radius:10px;border:0;background:#111827;color:white}}
          a{{color:#111827}}
          .muted{{color:#6b7280;font-size:13px}}
          .card{{border:1px solid #eee;border-radius:16px;padding:16px}}
        </style></head>
        <body>
          <div class="card">
            <h2 style="margin-top:0;">Paintly login</h2>
            <form method="post" action="/auth/login">
              <input type="hidden" name="next" value="{next}" />
              <label>Email</label>
              <input name="email" type="email" required />
              <label>Password</label>
              <input name="password" type="password" required />
              <button type="submit">Login</button>
            </form>
            <p class="muted" style="margin-bottom:0;margin-top:12px;">
              No account? <a href="/auth/register">Create one</a>
            </p>
          </div>
        </body></html>
        """
    )


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return HTMLResponse(
        """
        <!doctype html>
        <html><head><meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Register</title>
        <style>
          body{font-family:system-ui;margin:40px;max-width:420px}
          input{width:100%;padding:10px;margin:8px 0;border:1px solid #ddd;border-radius:10px}
          button{width:100%;padding:10px;border-radius:10px;border:0;background:#111827;color:white}
          a{color:#111827}
          .muted{color:#6b7280;font-size:13px}
          .card{border:1px solid #eee;border-radius:16px;padding:16px}
        </style></head>
        <body>
          <div class="card">
            <h2 style="margin-top:0;">Create your account</h2>
            <form method="post" action="/auth/register">
              <label>Company name</label>
              <input name="company_name" type="text" required />
              <label>Email</label>
              <input name="email" type="email" required />
              <label>Password</label>
              <input name="password" type="password" required />
              <button type="submit">Create account</button>
            </form>
            <p class="muted" style="margin-bottom:0;margin-top:12px;">
              Already have an account? <a href="/auth/login">Login</a>
            </p>
          </div>
        </body></html>
        """
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

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth.deps import get_current_user
from app.models.user import User
from app.models.lead import Lead

router = APIRouter(prefix="/app", tags=["app"])


def _login_redirect():
    return RedirectResponse(url="/auth/login", status_code=302)


@router.get("/leads", response_class=HTMLResponse)
def leads_page(
    request: Request,
    db: Session = Depends(get_db),
):
    # manual auth handling to redirect instead of JSON 401
    try:
        user: User = get_current_user(
            request=request, db=db
        )  # call dependency manually
    except Exception:
        return _login_redirect()

    tenant_ids = [user.tenant_id]

    # MVP/dev: ook public leads tonen (jouw intake maakt die aan als public)
    if "public" not in tenant_ids:
        tenant_ids.append("public")

    leads = (
        db.query(Lead)
        .filter(Lead.tenant_id.in_(tenant_ids))
        .order_by(Lead.id.desc())
        .limit(200)
        .all()
    )
    rows = ""
    for l in leads:
        open_btn = ""
        if l.estimate_html_key:
            open_btn = (
                f'<a href="/quotes/{l.id}/html" target="_blank">Open estimate</a>'
            )
        rows += f"""
        <tr>
          <td><a href="/app/leads/{l.id}">#{l.id}</a></td>
          <td>{l.name}<div class="muted">{l.email}</div></td>
          <td><span class="badge">{l.status}</span></td>
          <td>{open_btn}</td>
        </tr>
        """

    return HTMLResponse(
        f"""
    <!doctype html>
    <html><head><meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>Leads</title>
    <style>
      body{{font-family:system-ui;margin:24px}}
      .top{{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}}
      table{{width:100%;border-collapse:collapse}}
      th,td{{padding:10px;border-bottom:1px solid #eee;text-align:left;font-size:14px;vertical-align:top}}
      .badge{{padding:4px 8px;border-radius:999px;background:#f3f4f6;display:inline-block}}
      a.btn{{padding:10px 12px;border-radius:10px;background:#111827;color:#fff;text-decoration:none}}
      .muted{{color:#6b7280;font-size:13px}}
      form{{display:inline}}
      button.link{{background:none;border:0;color:#111827;text-decoration:underline;cursor:pointer;padding:0}}
    </style>
    </head><body>
      <div class="top">
        <div>
          <h2 style="margin:0;">Your leads</h2>
          <div class="muted">{user.email}</div>
        </div>
        <div>
          <a class="btn" href="/app/new">New estimate</a>
          <form method="post" action="/auth/logout" style="margin-left:8px;">
            <button class="link" type="submit">Logout</button>
          </form>
        </div>
      </div>

      <table>
        <thead><tr><th>ID</th><th>Customer</th><th>Status</th><th>Estimate</th></tr></thead>
        <tbody>
          {rows if rows else '<tr><td colspan="4" class="muted">No leads yet.</td></tr>'}
        </tbody>
      </table>
    </body></html>
    """
    )


@router.get("/leads/{lead_id}", response_class=HTMLResponse)
def lead_detail_page(
    lead_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        user: User = get_current_user(request=request, db=db)
    except Exception:
        return _login_redirect()

    # Fallback router compatibility:
    # delegate to the Paintly quote detail page so /app/leads/{lead_id}
    # always renders the full offerte-detail UI with quote actions.
    from app.verticals.paintly.router_app import app_lead_detail as paintly_lead_detail

    return paintly_lead_detail(
        request=request,
        lead_id=lead_id,
        db=db,
        current_user=user,
    )


@router.get("/new")
def new_estimate(request: Request):
    # MVP: redirect naar jouw intake entrypoint (Paintly demo tenant via slug)
    return RedirectResponse(url="/intake/paintly", status_code=302)

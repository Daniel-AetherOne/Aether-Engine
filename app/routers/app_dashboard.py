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

    leads = (
        db.query(Lead)
        .filter(Lead.tenant_id == user.tenant_id)
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
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        user: User = get_current_user(request=request, db=db)
    except Exception:
        return _login_redirect()

    lead = (
        db.query(Lead)
        .filter(Lead.id == lead_id, Lead.tenant_id == user.tenant_id)
        .first()
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    open_btn = ""
    if lead.estimate_html_key:
        open_btn = f'<a class="btn" href="/quotes/{lead.id}/html" target="_blank">Open estimate</a>'

    return HTMLResponse(
        f"""
    <!doctype html>
    <html><head><meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>Lead #{lead.id}</title>
    <style>
      body{{font-family:system-ui;margin:24px;max-width:900px}}
      .badge{{padding:4px 8px;border-radius:999px;background:#f3f4f6;display:inline-block}}
      a.btn{{padding:10px 12px;border-radius:10px;background:#111827;color:#fff;text-decoration:none;display:inline-block;margin-right:8px}}
      a.btn2{{padding:10px 12px;border-radius:10px;background:#e5e7eb;color:#111827;text-decoration:none;display:inline-block}}
      .card{{border:1px solid #eee;border-radius:14px;padding:14px;margin-top:12px}}
      .muted{{color:#6b7280;font-size:13px}}
    </style></head><body>
      <a class="btn2" href="/app/leads">← Back</a>
      <h2>Lead #{lead.id}</h2>
      <div class="muted">{lead.name} • {lead.email}</div>

      <div class="card">
        Status: <span class="badge">{lead.status}</span>
        {f'<div class="muted" style="margin-top:8px;">Error: {lead.error_message}</div>' if lead.error_message else ''}
      </div>

      <div class="card">
        {open_btn}
        <a class="btn2" href="/app/new">New estimate</a>
      </div>
    </body></html>
    """
    )


@router.get("/new")
def new_estimate(request: Request):
    # MVP: redirect naar jouw intake entrypoint
    return RedirectResponse(url="/intake/painters-us", status_code=302)

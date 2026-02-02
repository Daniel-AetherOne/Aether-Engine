from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.verticals.ace.api.dependencies.admin_auth import require_admin
from app.verticals.ace.domain.auth import AdminIdentity
from app.verticals.ace.audit_log import audit_db_path

router = APIRouter(prefix="/admin/audit", tags=["audit-admin"])
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)


def _parse_json(s: Optional[str]):
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return {"_raw": s}


@router.get("/view", response_class=HTMLResponse)
def audit_view(
    request: Request,
    admin: AdminIdentity = Depends(require_admin),
    action_type: Optional[str] = Query(None),
    day: Optional[str] = Query(None, description="YYYY-MM-DD (UTC)"),
    q: Optional[str] = Query(None, description="free search in actor/target/id"),
    limit: int = Query(50, ge=10, le=200),
    offset: int = Query(0, ge=0),
):
    db = audit_db_path()
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row

    where = []
    params = []

    if action_type:
        where.append("action_type = ?")
        params.append(action_type)

    if day:
        # filter by UTC date prefix in ISO string (created_at is ISO UTC)
        # e.g. 2026-01-16
        where.append("created_at LIKE ?")
        params.append(f"{day}%")

    if q:
        where.append(
            "(actor LIKE ? OR target_type LIKE ? OR target_id LIKE ? OR event_id LIKE ?)"
        )
        like = f"%{q}%"
        params.extend([like, like, like, like])

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
      SELECT
        event_id,
        created_at,
        actor,
        action_type,
        target_type,
        target_id,
        reason,
        old_json,
        new_json,
        meta_json
      FROM audit_events
      {where_sql}
      ORDER BY created_at DESC
      LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    rows = [dict(r) for r in con.execute(sql, params).fetchall()]

    # parse json for detail popup rendering
    for r in rows:
        r["old_value"] = _parse_json(r.get("old_json"))
        r["new_value"] = _parse_json(r.get("new_json"))
        r["meta"] = _parse_json(r.get("meta_json"))

    # actions list for filter dropdown
    actions = [
        row["action_type"]
        for row in con.execute(
            "SELECT DISTINCT action_type FROM audit_events WHERE action_type IS NOT NULL ORDER BY action_type"
        ).fetchall()
    ]

    return templates.TemplateResponse(
        "admin_audit.html",
        {
            "request": request,
            "items": rows,
            "actions": actions,
            "filters": {
                "action_type": action_type or "",
                "day": day or "",
                "q": q or "",
                "limit": limit,
                "offset": offset,
            },
        },
    )

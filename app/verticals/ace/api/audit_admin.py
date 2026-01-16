from __future__ import annotations

import json
import sqlite3
from fastapi import APIRouter, Depends, Query

from app.verticals.ace.api.dependencies.admin_auth import require_admin
from app.verticals.ace.domain.auth import AdminIdentity
from app.verticals.ace.audit_log import audit_db_path

router = APIRouter(prefix="/admin/audit", tags=["audit-admin"])


@router.get("")
def list_audit_events(
    admin: AdminIdentity = Depends(require_admin),
    quote_id: str | None = None,
    approval_id: str | None = None,
    event_type: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    db = audit_db_path()

    where = []
    params: list[object] = []

    if quote_id:
        where.append("quote_id = ?")
        params.append(quote_id)
    if approval_id:
        where.append("approval_id = ?")
        params.append(approval_id)
    if event_type:
        where.append("event_type = ?")
        params.append(event_type)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
      SELECT event_id, event_type, created_at, actor, quote_id, approval_id, meta_json
      FROM audit_events
      {where_sql}
      ORDER BY created_at DESC
      LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    with sqlite3.connect(db) as con:
        con.row_factory = sqlite3.Row
        raw_rows = con.execute(sql, params).fetchall()

    items = []
    for r in raw_rows:
        d = dict(r)
        # return meta as parsed JSON (dict) instead of a string
        try:
            d["meta"] = json.loads(d.pop("meta_json") or "{}")
        except Exception:
            d["meta"] = {"_raw": d.get("meta_json")}
            d.pop("meta_json", None)
        items.append(d)

    return {"ok": True, "count": len(items), "items": items}

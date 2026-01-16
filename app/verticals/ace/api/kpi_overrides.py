from __future__ import annotations

import os
import json
import sqlite3
from typing import Any, Dict

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/api/ace/kpi", tags=["ace", "kpi"])


def _audit_db_path() -> str:
    return os.getenv("AUDIT_DB_PATH", "audit.db")


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(_audit_db_path())
    con.row_factory = sqlite3.Row
    return con


def _get_meta_override_pct(meta_json: str | None) -> float | None:
    if not meta_json:
        return None
    try:
        d = json.loads(meta_json)
        v = d.get("overridePct")
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _get_meta_decision(meta_json: str | None) -> str | None:
    if not meta_json:
        return None
    try:
        d = json.loads(meta_json)
        v = d.get("decision")
        return str(v) if v else None
    except Exception:
        return None


@router.get("/overrides")
def kpi_overrides(days: int = Query(30, ge=1, le=365)) -> Dict[str, Any]:
    """
    6.8 — KPI’s for overrides from audit.db (MVP)
    - override_quote_count
    - approval_sent_count
    - approved/rejected counts
    - approval_rate
    - avg_override_pct
    """
    with _conn() as con:
        # unique quotes with an override request
        row = con.execute(
            """
            SELECT COUNT(DISTINCT quote_id) AS c
            FROM audit_events
            WHERE event_type = 'OVERRIDE_REQUESTED'
              AND quote_id IS NOT NULL
              AND created_at >= datetime('now', ?)
            """,
            (f"-{days} days",),
        ).fetchone()
        override_quote_count = int(row["c"] or 0)

        # number of approval sends
        row = con.execute(
            """
            SELECT COUNT(*) AS c
            FROM audit_events
            WHERE event_type = 'APPROVAL_SENT'
              AND created_at >= datetime('now', ?)
            """,
            (f"-{days} days",),
        ).fetchone()
        approval_sent_count = int(row["c"] or 0)

        # decisions (approved/rejected)
        rows = con.execute(
            """
            SELECT meta_json
            FROM audit_events
            WHERE event_type = 'APPROVAL_DECIDED'
              AND created_at >= datetime('now', ?)
            """,
            (f"-{days} days",),
        ).fetchall()

        approved_count = 0
        rejected_count = 0
        for r in rows:
            decision = _get_meta_decision(r["meta_json"])
            if decision == "APPROVED":
                approved_count += 1
            elif decision == "REJECTED":
                rejected_count += 1

        decided_total = approved_count + rejected_count
        approval_rate = (approved_count / decided_total) if decided_total > 0 else 0.0

        # avg override pct (from override requested)
        rows = con.execute(
            """
            SELECT meta_json
            FROM audit_events
            WHERE event_type = 'OVERRIDE_REQUESTED'
              AND created_at >= datetime('now', ?)
            """,
            (f"-{days} days",),
        ).fetchall()

        vals = []
        for r in rows:
            pct = _get_meta_override_pct(r["meta_json"])
            if pct is not None:
                vals.append(pct)

        avg_override_pct = (sum(vals) / len(vals)) if vals else 0.0

    return {
        "period_days": days,
        "override_quote_count": override_quote_count,
        "approval_sent_count": approval_sent_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "approval_rate": round(approval_rate, 4),
        "avg_override_pct": round(avg_override_pct, 4),
    }


@router.get("/overrides.csv", response_class=PlainTextResponse)
def kpi_overrides_csv(days: int = Query(30, ge=1, le=365)) -> str:
    """
    CSV export (MVP) — 1 row of aggregated KPI values.
    """
    data = kpi_overrides(days=days)
    header = ",".join(data.keys())
    row = ",".join(str(data[k]) for k in data.keys())
    return header + "\n" + row + "\n"

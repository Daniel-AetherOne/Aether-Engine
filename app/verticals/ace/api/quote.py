from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from uuid import uuid4
import hashlib

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from app.core.logging_config import logger
from app.verticals.ace.approval_store import ApprovalRecord, ApprovalStore
from app.verticals.ace.approval_tokens import ApprovalTokenService
from app.verticals.ace.schemas.quote_input_v1 import QuoteCalculateInputV1
from app.verticals.ace.schemas.quote_output_v1 import QuoteOutputV1
from app.verticals.ace.audit_log import AuditLog, audit_db_path
from app.verticals.ace.audit.logger import audit_logger, AuditWrite

# ----------------------------
# Routers
# ----------------------------
router = APIRouter(prefix="/api/ace/quote", tags=["ace", "quote"])
public_router = APIRouter(tags=["ace", "approval-public"])

# ----------------------------
# Template + Services (6.5)
# ----------------------------
templates = Jinja2Templates(directory="app/templates")

APPROVAL_TOKEN_SECRET = os.getenv(
    "APPROVAL_TOKEN_SECRET", "dev_secret_change_me_please"
)
APPROVAL_TOKEN_TTL_SECONDS = int(
    os.getenv("APPROVAL_TOKEN_TTL_SECONDS", "172800")
)  # 48h
APPROVAL_DB_PATH = os.getenv("APPROVAL_DB_PATH", "approvals.db")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")

token_svc = ApprovalTokenService(APPROVAL_TOKEN_SECRET)
store = ApprovalStore(APPROVAL_DB_PATH)


# ----------------------------
# Helpers
# ----------------------------
def classify_result(engine_payload: dict) -> str:
    blocking = engine_payload.get("blocking") or []
    warnings = engine_payload.get("warnings") or []
    if blocking:
        return "blocking"
    if warnings:
        return "warning"
    return "ok"


def get_customer_id(payload: QuoteCalculateInputV1) -> str | None:
    return payload.context.customer_id if payload.context else None


def _calculate_engine_payload(payload: QuoteCalculateInputV1) -> dict[str, Any]:
    """Demo engine logic (shared by calculate/export/approval)."""
    lines: list[dict[str, Any]] = []
    total_sell = 0.0

    for item in payload.items:
        net_sell = item.qty * 100  # demo prijs
        margin_pct = 0.2
        total_sell += net_sell

        lines.append(
            {
                "sku": item.sku,
                "qty": item.qty,
                "netSell": net_sell,
                "marginPct": margin_pct,
                "priceBreakdown": [
                    f"Base price: {item.qty} × 100",
                    "Margin: 20%",
                ],
            }
        )

    warnings: list[str] = []
    blocking: list[str] = []

    if total_sell > 500:
        warnings.append("Approval required: totalSell exceeds limit")

    for item in payload.items:
        if item.qty > 1000:
            blocking.append(f"Qty too high for SKU {item.sku}")

    return {
        "quoteId": "demo",
        "totalSell": total_sell,
        "marginPct": 0.2,
        "validUntil": "2026-12-31",
        "lines": lines,
        "warnings": warnings,
        "blocking": blocking,
    }


def _has_blocking(engine_payload: dict[str, Any]) -> bool:
    blocking = engine_payload.get("blocking") or []
    return isinstance(blocking, list) and len(blocking) > 0


def _log_obs(
    *,
    request: Request,
    endpoint: str,
    payload: QuoteCalculateInputV1,
    duration_ms: float,
    result: str,
    event: str,
    status_code: int | None = None,
):
    request_id = getattr(request.state, "request_id", None) or request.headers.get(
        "X-Request-ID", "unknown"
    )

    bound = logger.bind(
        request_id=request_id,
        customer_id=get_customer_id(payload),
        line_count=len(payload.items or []),
        duration_ms=duration_ms,
        result=result,
        endpoint=endpoint,
    )
    if status_code is not None:
        bound = bound.bind(status_code=status_code)

    bound.info(event)


# ----------------------------
# 1) Calculate
# ----------------------------
@router.post("/calculate", response_model=QuoteOutputV1)
def calculate_quote(payload: QuoteCalculateInputV1, request: Request) -> QuoteOutputV1:
    t0 = time.time()

    engine_payload = _calculate_engine_payload(payload)
    result = classify_result(engine_payload)
    duration_ms = round((time.time() - t0) * 1000, 2)

    _log_obs(
        request=request,
        endpoint="/api/ace/quote/calculate",
        payload=payload,
        duration_ms=duration_ms,
        result=result,
        event="quote_calculate",
        status_code=200,
    )

    blocking = engine_payload.get("blocking") or []

    return QuoteOutputV1(
        calculation_id="demo",
        engine_version="dev",
        status="ok" if not blocking else "blocking",
        payload=engine_payload,
    )


# ----------------------------
# 2) Export XLSX (5.5 + 6.6 gate)
# ----------------------------
@router.post("/export/xlsx")
def export_xlsx(
    payload: QuoteCalculateInputV1,
    request: Request,
    approvalId: str | None = None,
) -> StreamingResponse:
    t0 = time.time()

    engine_payload = _calculate_engine_payload(payload)

    # hard block blijft altijd
    if _has_blocking(engine_payload):
        duration_ms = round((time.time() - t0) * 1000, 2)
        _log_obs(
            request=request,
            endpoint="/api/ace/quote/export/xlsx",
            payload=payload,
            duration_ms=duration_ms,
            result="blocking",
            event="quote_export_xlsx",
            status_code=409,
        )
        raise HTTPException(status_code=409, detail="Cannot export while blocking.")

    # 6.6 — export gate: als approvalId meegegeven is, moet hij APPROVED zijn
    if approvalId:
        try:
            rec = store.get(approvalId)
        except KeyError:
            raise HTTPException(status_code=404, detail="Approval not found.")

        if rec.status != "APPROVED":
            raise HTTPException(
                status_code=409,
                detail=f"Cannot export: approval status is {rec.status}.",
            )

    # Create workbook
    try:
        from openpyxl import Workbook
    except Exception as e:
        duration_ms = round((time.time() - t0) * 1000, 2)
        _log_obs(
            request=request,
            endpoint="/api/ace/quote/export/xlsx",
            payload=payload,
            duration_ms=duration_ms,
            result="error",
            event="quote_export_xlsx",
            status_code=500,
        )
        raise HTTPException(
            status_code=500, detail=f"openpyxl missing or failed to import: {e}"
        )

    wb = Workbook()
    ws = wb.active
    ws.title = "Quote"

    # Summary
    ws.append(["quoteId", engine_payload.get("quoteId", "")])
    ws.append(["totalSell", engine_payload.get("totalSell", "")])
    ws.append(["marginPct", engine_payload.get("marginPct", "")])
    ws.append(["validUntil", engine_payload.get("validUntil", "")])
    ws.append([])

    # Lines
    ws.append(["SKU", "Qty", "netSell", "marginPct"])
    for ln in engine_payload.get("lines", []):
        ws.append(
            [
                ln.get("sku", ""),
                ln.get("qty", ""),
                ln.get("netSell", ""),
                ln.get("marginPct", ""),
            ]
        )

    # Warnings/Blocking
    ws.append([])
    ws.append(["Warnings"])
    for w in engine_payload.get("warnings", []):
        ws.append([w])

    ws.append([])
    ws.append(["Blocking"])
    for b in engine_payload.get("blocking", []):
        ws.append([b])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    duration_ms = round((time.time() - t0) * 1000, 2)
    _log_obs(
        request=request,
        endpoint="/api/ace/quote/export/xlsx",
        payload=payload,
        duration_ms=duration_ms,
        result=classify_result(engine_payload),
        event="quote_export_xlsx",
        status_code=200,
    )

    filename = f"quote_{engine_payload.get('quoteId','quote')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ----------------------------
# 3) Send approval (6.5)
# ----------------------------
@router.post("/approval/send")
def send_approval(
    payload: QuoteCalculateInputV1,
    request: Request,
    overridePct: float,
    reason: str,
    requestedBy: str,
) -> dict[str, Any]:
    """
    6.5 — MVP: manager kan beslissen via email, zonder UI/login.
    overridePct/reason/requestedBy zijn expliciet (geen 'stiekem').
    """
    t0 = time.time()

    engine_payload = _calculate_engine_payload(payload)

    if _has_blocking(engine_payload):
        duration_ms = round((time.time() - t0) * 1000, 2)
        _log_obs(
            request=request,
            endpoint="/api/ace/quote/approval/send",
            payload=payload,
            duration_ms=duration_ms,
            result="blocking",
            event="quote_send_approval",
            status_code=409,
        )
        raise HTTPException(
            status_code=409, detail="Cannot send approval while blocking."
        )

    if not reason or len(reason.strip()) < 10:
        raise HTTPException(
            status_code=422, detail="reason is required (min 10 chars)."
        )
    if overridePct <= 0:
        raise HTTPException(status_code=422, detail="overridePct must be > 0.")
    if not requestedBy:
        raise HTTPException(status_code=422, detail="requestedBy is required.")

    warnings = engine_payload.get("warnings") or []
    approval_required = any("approval required" in str(w).lower() for w in warnings)
    if not approval_required:
        duration_ms = round((time.time() - t0) * 1000, 2)
        _log_obs(
            request=request,
            endpoint="/api/ace/quote/approval/send",
            payload=payload,
            duration_ms=duration_ms,
            result="ok",
            event="quote_send_approval",
            status_code=400,
        )
        raise HTTPException(
            status_code=400, detail="Approval not required for this quote."
        )

    # 6.7 audit: override requested
    audit_logger.log(
        AuditWrite(
            action_type=EVENT_TYPE_HIER,  # bv. "OVERRIDE_REQUESTED" of "APPROVAL_SENT"
            actor=ACTOR_HIER,  # bv. admin / "system" / "manager_via_link"
            target_type=TARGET_TYPE_HIER,  # bv. "QUOTE" / "APPROVAL"
            target_id=TARGET_ID_HIER,  # bv. quote_id of approval_id
            quote_id=quote_id if "quote_id" in locals() else None,
            approval_id=approval_id if "approval_id" in locals() else None,
            reason=REASON_HIER,  # verplicht voor OVERRIDE_REQUESTED
            old_value=OLD_HIER,  # optioneel
            new_value=NEW_HIER,  # optioneel
            meta=META_HIER,  # dict
            audit_id=EVENT_ID_HIER,  # jouw bestaande event_id string
        )
    )

    approval_id = uuid4().hex
    quote_id = str(engine_payload.get("quoteId") or "demo")

    rec = ApprovalRecord(
        approval_id=approval_id,
        quote_id=quote_id,
        status="PENDING_APPROVAL",
        requested_by=requestedBy,
        override_pct=float(overridePct),
        reason=reason.strip(),
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    store.create(rec)

    # 6.7 audit: approval sent (record created)
    audit_logger.log(
        AuditWrite(
            action_type=EVENT_TYPE_HIER,  # bv. "OVERRIDE_REQUESTED" of "APPROVAL_SENT"
            actor=ACTOR_HIER,  # bv. admin / "system" / "manager_via_link"
            target_type=TARGET_TYPE_HIER,  # bv. "QUOTE" / "APPROVAL"
            target_id=TARGET_ID_HIER,  # bv. quote_id of approval_id
            quote_id=quote_id if "quote_id" in locals() else None,
            approval_id=approval_id if "approval_id" in locals() else None,
            reason=REASON_HIER,  # verplicht voor OVERRIDE_REQUESTED
            old_value=OLD_HIER,  # optioneel
            new_value=NEW_HIER,  # optioneel
            meta=META_HIER,  # dict
            audit_id=EVENT_ID_HIER,  # jouw bestaande event_id string
        )
    )

    token = token_svc.make(approval_id=approval_id, quote_id=quote_id)
    approve_url = f"{PUBLIC_BASE_URL}/approval/approve/{token}"
    reject_url = f"{PUBLIC_BASE_URL}/approval/reject/{token}"

    # waarom approval nodig is: neem de eerste passende warning
    why = next(
        (str(w) for w in warnings if "approval" in str(w).lower()), "Approval vereist."
    )

    html = templates.get_template("approval_email.html").render(
        quote=engine_payload,
        customer_id=get_customer_id(payload),
        override_pct=float(overridePct),
        reason=reason.strip(),
        why_approval=why,
        approve_url=approve_url,
        reject_url=reject_url,
    )

    # MVP: geen mail provider in deze fase => log/render output
    logger.bind(approval_id=approval_id, quote_id=quote_id).info(
        "approval_email_rendered"
    )

    duration_ms = round((time.time() - t0) * 1000, 2)
    _log_obs(
        request=request,
        endpoint="/api/ace/quote/approval/send",
        payload=payload,
        duration_ms=duration_ms,
        result="ok",
        event="quote_send_approval",
        status_code=200,
    )

    return {
        "status": "sent_stub",
        "approvalId": approval_id,
        "quoteId": quote_id,
        "approveUrl": approve_url,
        "rejectUrl": reject_url,
        "emailHtmlPreview": html,
    }


@router.get("/approval/status/{approval_id}")
def approval_status(approval_id: str) -> dict[str, Any]:
    try:
        rec = store.get(approval_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Approval not found.")

    return {
        "approvalId": rec.approval_id,
        "quoteId": rec.quote_id,
        "status": rec.status,
        "decidedAt": rec.decided_at,
        "tokenUsedAt": rec.token_used_at,
    }


# ----------------------------
# 4) Public approve/reject (6.6 hardened)
# ----------------------------
def _token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _approval_decided_event_id(
    *, approval_id: str, decision: str, token_hash: str
) -> str:
    # Deterministic + unique => prevents duplicate APPROVAL_DECIDED entries on double-click
    base = f"APPROVAL_DECIDED:{approval_id}:{decision}:{token_hash}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


@public_router.get("/approval/approve/{token}", response_class=HTMLResponse)
def approval_approve(token: str, request: Request) -> HTMLResponse:
    try:
        payload = token_svc.verify(token, max_age_seconds=APPROVAL_TOKEN_TTL_SECONDS)
    except ValueError as e:
        code = str(e)
        msg = "Link verlopen." if code == "TOKEN_EXPIRED" else "Ongeldige link."
        return HTMLResponse(f"<h3>{msg}</h3>", status_code=400)

    approval_id = payload.get("approval_id")
    quote_id = payload.get("quote_id")

    if not approval_id or not quote_id:
        return HTMLResponse(
            "<h3>Ongeldige link (payload incompleet).</h3>", status_code=400
        )

    # Load record to verify quote_id matches (anti-tamper)
    try:
        rec0 = store.get(approval_id)
    except KeyError:
        return HTMLResponse("<h3>Approval niet gevonden.</h3>", status_code=404)

    if rec0.quote_id != quote_id:
        return HTMLResponse(
            "<h3>Ongeldige link (quote mismatch).</h3>", status_code=400
        )

    token_hash = _token_sha256(token)
    rec = store.decide_once(approval_id, "APPROVED", decision_token_hash=token_hash)

    # 6.7 audit: idempotent decided event (no duplicates)
    eid = _approval_decided_event_id(
        approval_id=rec.approval_id,
        decision="APPROVED",
        token_hash=token_hash,
    )

    audit_logger.log_deduped(
        AuditWrite(
            action_type=EVENT_TYPE_HIER,
            actor=ACTOR_HIER,
            target_type=TARGET_TYPE_HIER,
            target_id=TARGET_ID_HIER,
            quote_id=quote_id if "quote_id" in locals() else None,
            approval_id=approval_id if "approval_id" in locals() else None,
            reason=REASON_HIER,
            old_value=OLD_HIER,
            new_value=NEW_HIER,
            meta=META_HIER,
            audit_id=EVENT_ID_HIER,
        )
    )

    # If already processed before this click, user still sees a friendly message
    if rec.status == "APPROVED":
        if rec.token_used_at is not None and rec.decided_at is not None:
            return HTMLResponse("<h3>✅ Approved. Bedankt!</h3>", status_code=200)
        return HTMLResponse("<h3>✅ Approved. Bedankt!</h3>", status_code=200)

    if rec.status == "REJECTED":
        return HTMLResponse(
            "<h3>Deze aanvraag is al verwerkt (REJECTED).</h3>", status_code=200
        )

    return HTMLResponse(
        "<h3>Deze aanvraag kon niet worden verwerkt.</h3>", status_code=409
    )


@public_router.get("/approval/reject/{token}", response_class=HTMLResponse)
def approval_reject(token: str, request: Request) -> HTMLResponse:
    # NOTE: removed the buggy audit.append that referenced rec/token_hash before they existed

    try:
        payload = token_svc.verify(token, max_age_seconds=APPROVAL_TOKEN_TTL_SECONDS)
    except ValueError as e:
        code = str(e)
        msg = "Link verlopen." if code == "TOKEN_EXPIRED" else "Ongeldige link."
        return HTMLResponse(f"<h3>{msg}</h3>", status_code=400)

    approval_id = payload.get("approval_id")
    quote_id = payload.get("quote_id")

    if not approval_id or not quote_id:
        return HTMLResponse(
            "<h3>Ongeldige link (payload incompleet).</h3>", status_code=400
        )

    # Load record to verify quote_id matches (anti-tamper)
    try:
        rec0 = store.get(approval_id)
    except KeyError:
        return HTMLResponse("<h3>Approval niet gevonden.</h3>", status_code=404)

    if rec0.quote_id != quote_id:
        return HTMLResponse(
            "<h3>Ongeldige link (quote mismatch).</h3>", status_code=400
        )

    token_hash = _token_sha256(token)
    rec = store.decide_once(approval_id, "REJECTED", decision_token_hash=token_hash)

    # 6.7 audit: idempotent decided event (no duplicates)
    eid = _approval_decided_event_id(
        approval_id=rec.approval_id,
        decision="REJECTED",
        token_hash=token_hash,
    )

    audit_logger.log_deduped(
        AuditWrite(
            action_type=EVENT_TYPE_HIER,
            actor=ACTOR_HIER,
            target_type=TARGET_TYPE_HIER,
            target_id=TARGET_ID_HIER,
            quote_id=quote_id if "quote_id" in locals() else None,
            approval_id=approval_id if "approval_id" in locals() else None,
            reason=REASON_HIER,
            old_value=OLD_HIER,
            new_value=NEW_HIER,
            meta=META_HIER,
            audit_id=EVENT_ID_HIER,
        )
    )

    if rec.status == "REJECTED":
        return HTMLResponse("<h3>❌ Rejected. Bedankt!</h3>", status_code=200)

    if rec.status == "APPROVED":
        return HTMLResponse(
            "<h3>Deze aanvraag is al verwerkt (APPROVED).</h3>", status_code=200
        )

    return HTMLResponse(
        "<h3>Deze aanvraag kon niet worden verwerkt.</h3>", status_code=409
    )

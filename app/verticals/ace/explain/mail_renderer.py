from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Tuple

from app.verticals.ace.explain.formatter import (
    format_notices_header,
    format_steps_bullets_text,
)


def _as_payload(out: Any) -> Dict[str, Any]:
    if isinstance(out, dict):
        return out
    if is_dataclass(out):
        return asdict(out)
    raise TypeError("render_approval_email expects QuoteOutputV1 or dict payload")


def render_approval_email(out: Any) -> Tuple[str, str]:
    """
    Returns (subject, body_text).

    Policy:
    - If blocks[] not empty: subject indicates BLOCKED and body explains why.
      (Later: caller can decide 'do not send'.)
    - Else: warnings header + per-line bullets with steps
    """
    p = _as_payload(out)

    status = (p.get("status") or "OK").upper()
    quote_id = p.get("quote_id") or p.get("id") or ""  # if you have it; otherwise blank
    total = (p.get("total") or {}).get("amount")
    currency = p.get("currency") or (p.get("total") or {}).get("currency") or "EUR"

    blocks = p.get("blocks") or []
    warnings = p.get("warnings") or []
    lines = p.get("lines") or []

    # Subject
    if blocks:
        subject = f"[BLOCKED] Quote requires fix{f' ({quote_id})' if quote_id else ''}"
    elif warnings:
        subject = f"[APPROVAL REQUIRED] Quote needs review{f' ({quote_id})' if quote_id else ''}"
    else:
        subject = f"[OK] Quote ready{f' ({quote_id})' if quote_id else ''}"

    # Body
    parts = []
    if total is not None:
        parts.append(f"Total: {currency} {total}")
    if quote_id:
        parts.append(f"Quote ID: {quote_id}")
    parts.append(f"Status: {status}")
    parts.append("")

    if blocks:
        parts.append(format_notices_header("BLOCKING (hard stop)", blocks))
        parts.append("")
        parts.append("This quote may not be exported/approved until blocking issues are resolved.")
        parts.append("")
        # Optional: still show per-line steps for debugging
    else:
        if warnings:
            parts.append(format_notices_header("WARNINGS (approval / attention)", warnings))
            parts.append("")

    parts.append("LINES")
    parts.append("-----")

    for line in lines:
        line_id = line.get("line_id")
        sku = line.get("sku")
        qty = line.get("qty")
        net_sell = (line.get("net_sell") or {}).get("amount")
        steps = line.get("steps") or []

        parts.append(f"- Line {line_id} | SKU={sku} | qty={qty} | netSell={currency} {net_sell}")
        if steps:
            parts.append(format_steps_bullets_text(steps))
        else:
            parts.append("• (no breakdown steps)")
        parts.append("")

    body = "\n".join(parts).rstrip() + "\n"
    return subject, body

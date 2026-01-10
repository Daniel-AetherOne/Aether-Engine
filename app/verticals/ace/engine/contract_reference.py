from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List

from dateutil.parser import isoparse

VERTICAL_ID_V1 = "ace-wholesale"
CONTRACT_VERSION_V1 = "v1"


def _canonical_json(obj: Any) -> str:
    """Deterministic JSON string: sorted keys, no whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _money_2dp(value: Decimal) -> str:
    q = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{q:.2f}"


def _pct(value: Decimal) -> str:
    q = value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return f"{q:.4f}"


def compute_quote_id_v1(input_payload: Dict[str, Any]) -> str:
    material = {
        "contractVersion": CONTRACT_VERSION_V1,
        "verticalId": VERTICAL_ID_V1,
        "input": input_payload,
    }
    digest = _sha256_hex(_canonical_json(material))
    return "q_" + digest[:16]


def generate_quote_v1(input_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reference implementation for contract tests only.
    NOT pricing logic. Produces contract-compliant output deterministically.
    """
    as_of: date = isoparse(input_payload["asOfDate"]).date()
    valid_until: date = as_of.fromordinal(as_of.toordinal() + 14)

    quote_id = compute_quote_id_v1(input_payload)

    lines_out: List[Dict[str, Any]] = []
    total_sell = Decimal("0.00")
    quote_margin = Decimal("0.0000")  # placeholder

    for i, line in enumerate(input_payload["lines"], start=1):
        sku = line["sku"]
        qty = int(line["qty"])

        # placeholder pricing (contract-only)
        net_sell = Decimal("0.00")
        line_margin = Decimal("0.0000")

        # explainability: non-empty, format-compliant (v1)
        price_breakdown = [
            f"{i:02d}. RULE base_price | +0.00 | inputs:sku={sku} | reason:Contract reference base",
            f"{i:02d}. RULE qty_capture | +0.00 | inputs:qty={qty} | reason:Contract reference qty",
        ]

        lines_out.append(
            {
                "sku": sku,
                "qty": qty,
                "netSell": _money_2dp(net_sell),
                "marginPct": _pct(line_margin),
                "priceBreakdown": price_breakdown,
            }
        )

        total_sell += net_sell

    return {
        "quoteId": quote_id,
        "quoteDate": as_of.isoformat(),
        "validUntil": valid_until.isoformat(),
        "contractVersion": CONTRACT_VERSION_V1,
        "currency": input_payload["currency"],
        "lines": lines_out,
        "totalSell": _money_2dp(total_sell),
        "marginPct": _pct(quote_margin),
        "warnings": [],
        "blocking": [],
    }

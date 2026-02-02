from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List

from app.verticals.painters_us.pricing_output_schema import (
    PricingLineItem,
    PricingMeta,
    PricingOutput,
    PricingSubtotals,
    PricingTotals,
)


def _val(obj: Any, key: str, default: Any = None) -> Any:
    """
    Safe getter that supports both dicts and objects (e.g. Pydantic models/dataclasses).
    """
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _to_decimal(val: Any, default: Decimal = Decimal("0.00")) -> Decimal:
    if val is None:
        return default
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _to_date(val: Any) -> date:
    """
    Accepts:
      - ISO date string (YYYY-MM-DD)
      - datetime.date
      - datetime.datetime
      - None
    Returns a date (defaults to today if invalid).
    """
    if val is None:
        return date.today()

    # datetime is also a date subclass, so check datetime first
    if isinstance(val, datetime):
        return val.date()

    if isinstance(val, date):
        return val

    if isinstance(val, str):
        try:
            return date.fromisoformat(val)
        except Exception:
            return date.today()

    return date.today()


def build_pricing_output_from_legacy(
    *,
    pricing_output: Dict[str, Any],
    items: List[Any],  # can be list[dict] OR list[EstimateItem]
    project: Dict[str, Any],
) -> PricingOutput:
    """
    Adapter: takes your current `pricing_output` dict + mapped `items` and produces
    the canonical PricingOutput schema.

    Keeps behavior identical, just normalizes & validates.
    """

    # ---- meta ----
    meta = PricingMeta(
        estimate_id=str(project.get("estimate_id") or ""),
        date=_to_date(project.get("date")),
        valid_until=(
            _to_date(project.get("valid_until")) if project.get("valid_until") else None
        ),
        currency="USD",
    )

    # ---- line items ----
    line_items: List[PricingLineItem] = []
    for idx, it in enumerate(items, start=1):
        # map_surfaces_to_items may return dicts OR EstimateItem objects
        total = _val(it, "total_usd")
        if total is None:
            # If not priced yet, skip canonical line items
            continue

        qty_raw = _val(it, "quantity") or 0
        try:
            qty = float(qty_raw)
        except (ValueError, TypeError):
            qty = 0.0
        if qty <= 0:
            continue

        total_dec = _to_decimal(total)
        qty_dec = _to_decimal(qty, default=Decimal("0.00"))
        if qty_dec == 0:
            continue

        unit_price = total_dec / qty_dec

        # Notes/description (support both field names)
        desc = _val(it, "notes")
        if desc is None:
            desc = _val(it, "description")

        line_items.append(
            PricingLineItem(
                code=str(_val(it, "code") or f"item_{idx}"),
                label=str(_val(it, "label") or f"Item {idx}"),
                description=str(desc) if desc else None,
                quantity=qty,
                unit=str(_val(it, "unit") or "unit"),
                unit_price=unit_price,
                total=total_dec,
                category=str(_val(it, "category") or "labor"),
                assumptions={
                    "prep_level": _val(it, "prep_level"),
                    "access": _val(it, "access_risk"),
                },
            )
        )

    labor = _to_decimal(pricing_output.get("labor_usd"))
    materials = _to_decimal(pricing_output.get("materials_usd"))

    pre_tax = pricing_output.get("total_usd")
    # If pricing not ready, total_usd might be None. Keep it 0 in schema until ready.
    pre_tax_amount = _to_decimal(pre_tax)

    totals = PricingTotals(
        pre_tax=pre_tax_amount,
        grand_total=pre_tax_amount,  # tax placeholder later
    )

    subtotals = PricingSubtotals(
        labor=labor,
        materials=materials,
    )

    # optional tax placeholder (not used yet)
    tax = None

    return PricingOutput(
        meta=meta,
        line_items=line_items,
        subtotals=subtotals,
        totals=totals,
        tax=tax,
        notes=[],
    )


# -------------------------
# Pipeline compatibility wrapper
# -------------------------
def build_pricing_output(
    lead: Any, vision: Any, pricing: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Pipeline expects: build_pricing_output(lead, vision, pricing) -> JSON-serializable dict.

    Internally, we normalize into PricingOutput schema via build_pricing_output_from_legacy,
    then return .model_dump() (Pydantic v2) or .dict() (Pydantic v1) depending on your schema models.
    """
    today = date.today()

    # The legacy adapter expects:
    # - pricing_output: dict with totals fields (we pass `pricing`)
    # - items: list of dicts/objects with quantity + total_usd, etc.
    #   Your pricing_engine_us returns `line_items` with base_total_usd, not total_usd.
    #   We'll map minimally so totals render.
    raw_items: List[Any] = []
    for li in (pricing or {}).get("line_items", []) or []:
        if isinstance(li, dict):
            # map base_total_usd -> total_usd if needed
            if li.get("total_usd") is None and li.get("base_total_usd") is not None:
                li = {**li, "total_usd": li.get("base_total_usd")}
            # ensure quantity key exists
            if li.get("quantity") is None:
                li = {**li, "quantity": li.get("sqft") or li.get("count") or 1}
            raw_items.append(li)
        else:
            raw_items.append(li)

    project = {
        "estimate_id": f"lead_{getattr(lead, 'id', '')}",
        "date": today.isoformat(),
        # 30d validity default
        "valid_until": (today + timedelta(days=30)).isoformat(),
    }

    out = build_pricing_output_from_legacy(
        pricing_output=pricing or {},
        items=raw_items,
        project=project,
    )

    # Return JSON-friendly dict regardless of Pydantic version
    if hasattr(out, "model_dump"):
        return out.model_dump()
    if hasattr(out, "dict"):
        return out.dict()

    # Fallback (should not happen): return minimal representation
    return {"meta": {}, "line_items": [], "subtotals": {}, "totals": {}}

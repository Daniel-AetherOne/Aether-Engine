from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Union

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
        estimate_id=str(project["estimate_id"]),
        date=date.fromisoformat(project["date"]),
        valid_until=(
            date.fromisoformat(project["valid_until"])
            if project.get("valid_until")
            else None
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

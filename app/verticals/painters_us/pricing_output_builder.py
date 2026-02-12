from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from app.verticals.painters_us.pricing_output_schema import (
    PricingLineItem,
    PricingMeta,
    PricingOutput,
    PricingSubtotals,
    PricingTotals,
)


# -------------------------
# Helpers
# -------------------------
def _val(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _to_decimal(
    val: Any, default: Optional[Decimal] = Decimal("0.00")
) -> Optional[Decimal]:
    """
    Convert to Decimal. If val is None -> returns `default`.
    If you want to preserve None, pass default=None.
    """
    if val is None:
        return default
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _to_date(val: Any) -> date:
    if val is None:
        return date.today()
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


def _pick_first(d: Dict[str, Any], keys: List[str]) -> Any:
    for k in keys:
        if k in d and d.get(k) is not None:
            return d.get(k)
    return None


def _as_list(x: Any) -> List[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return []


def _guess_category(it: Any) -> str:
    cat = _val(it, "category")
    if isinstance(cat, str) and cat.strip():
        return cat.strip().lower()

    t = _val(it, "type") or _val(it, "kind")
    if isinstance(t, str) and t.strip():
        t2 = t.strip().lower()
        if "material" in t2:
            return "materials"
        if "labor" in t2:
            return "labor"

    return "labor"


def _extract_qty(it: Any) -> float:
    for k in ["quantity", "qty", "sqft", "square_feet", "area_sqft", "count", "units"]:
        v = _val(it, k)
        if v is None:
            continue
        try:
            f = float(v)
            if f > 0:
                return f
        except Exception:
            continue
    return 0.0


def _extract_total_usd(it: Any) -> Optional[Decimal]:
    for k in [
        "total_usd",
        "line_total_usd",
        "amount_usd",
        "base_total_usd",
        "total",
        "amount",
    ]:
        v = _val(it, k)
        if v is None:
            continue
        dec = _to_decimal(v, default=Decimal("0.00"))
        if dec and dec != Decimal("0.00"):
            return dec

    unit_price = (
        _val(it, "unit_price") or _val(it, "unit_price_usd") or _val(it, "price_usd")
    )
    qty = _extract_qty(it)
    if unit_price is not None and qty > 0:
        up = _to_decimal(unit_price, default=Decimal("0.00"))
        if up and up != Decimal("0.00"):
            return up * (_to_decimal(qty, default=Decimal("0.00")) or Decimal("0.00"))

    return None


def _coerce_pricing_dict(pricing: Any) -> Dict[str, Any]:
    """
    Accept dict OR StepResult-like object with .data dict.
    """
    if pricing is None:
        return {}
    if isinstance(pricing, dict):
        return pricing
    # StepResult(status=..., data={...})
    data = getattr(pricing, "data", None)
    if isinstance(data, dict):
        return data
    # Pydantic models etc.
    if hasattr(pricing, "model_dump"):
        try:
            d = pricing.model_dump()
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}
    if hasattr(pricing, "dict"):
        try:
            d = pricing.dict()
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}
    return {}


# -------------------------
# Legacy -> schema builder
# -------------------------
def build_pricing_output_from_legacy(
    *,
    pricing_output: Dict[str, Any],
    items: List[Any],
    project: Dict[str, Any],
) -> PricingOutput:
    meta = PricingMeta(
        estimate_id=str(project.get("estimate_id") or ""),
        date=_to_date(project.get("date")),
        valid_until=(
            _to_date(project.get("valid_until")) if project.get("valid_until") else None
        ),
        currency="USD",
    )

    line_items: List[PricingLineItem] = []
    for idx, it in enumerate(items, start=1):
        total_dec = _extract_total_usd(it)
        if total_dec is None:
            continue

        qty = _extract_qty(it)
        # IMPORTANT: don't drop items just because qty is missing upstream
        if qty <= 0:
            qty = 1.0

        qty_dec = _to_decimal(qty, default=Decimal("0.00")) or Decimal("0.00")
        if qty_dec == 0:
            qty_dec = Decimal("1.00")

        unit_price = total_dec / qty_dec

        desc = _val(it, "notes")
        if desc is None:
            desc = _val(it, "description")

        line_items.append(
            PricingLineItem(
                code=str(_val(it, "code") or _val(it, "id") or f"item_{idx}"),
                label=str(_val(it, "label") or _val(it, "name") or f"Item {idx}"),
                description=str(desc) if desc else None,
                quantity=float(qty),
                unit=str(_val(it, "unit") or _val(it, "uom") or "job"),
                unit_price=unit_price,
                total=total_dec,
                category=_guess_category(it),
                assumptions={
                    "prep_level": _val(it, "prep_level"),
                    "access": _val(it, "access_risk") or _val(it, "access"),
                },
            )
        )

    labor = _to_decimal(
        pricing_output.get("labor_usd"), default=Decimal("0.00")
    ) or Decimal("0.00")
    materials = _to_decimal(
        pricing_output.get("materials_usd"), default=Decimal("0.00")
    ) or Decimal("0.00")

    # IMPORTANT: preserve None if missing, so we can compute from items instead of defaulting to 0.00
    pre_tax_amount = _to_decimal(pricing_output.get("total_usd"), default=None)

    if pre_tax_amount is None:
        # Try compute from items totals
        s = Decimal("0.00")
        any_item = False
        for li in line_items:
            if li.total is not None:
                any_item = True
                s += li.total
        if any_item and s != Decimal("0.00"):
            pre_tax_amount = s
        else:
            # fallback to labor+materials
            if (labor + materials) != Decimal("0.00"):
                pre_tax_amount = labor + materials
            else:
                pre_tax_amount = Decimal("0.00")

    totals = PricingTotals(pre_tax=pre_tax_amount, grand_total=pre_tax_amount)
    subtotals = PricingSubtotals(labor=labor, materials=materials)

    return PricingOutput(
        meta=meta,
        line_items=line_items,
        subtotals=subtotals,
        totals=totals,
        tax=None,
        notes=[],
    )


# -------------------------
# Main builder used by pipeline
# -------------------------
def build_pricing_output(lead: Any, vision: Any, pricing: Any) -> Dict[str, Any]:
    """
    OPTION 1 (MVP):
    - If pricing.total_usd is missing but pricing.estimate_range exists,
      show a provisional total (choose high_usd else low_usd).
    - If estimate_range exists but is 0/None, still show a minimum provisional total
      so customer never sees $0.00/TBD.
    """
    today = date.today()

    # ✅ Accept dict OR StepResult-like with .data
    pricing = _coerce_pricing_dict(pricing)

    # 1) items from multiple possible keys
    raw_items = (
        pricing.get("line_items")
        or pricing.get("items")
        or pricing.get("breakdown")
        or pricing.get("rows")
        or []
    )
    raw_items = _as_list(raw_items)

    # 2) total (normal)
    total_usd = _pick_first(
        pricing, ["total_usd", "grand_total_usd", "grand_total", "total"]
    )
    total_dec: Optional[Decimal] = None
    if total_usd is not None:
        td = _to_decimal(total_usd, default=Decimal("0.00"))
        if td and td != Decimal("0.00"):
            total_dec = td

    # 3) fallback: sum items
    if total_dec is None and raw_items:
        s = Decimal("0.00")
        any_item = False
        for it in raw_items:
            t = _extract_total_usd(it)
            if t is not None:
                any_item = True
                s += t
        if any_item and s != Decimal("0.00"):
            total_dec = s

    # 4) ✅ OPTION 1 fallback: estimate_range (and if 0/None -> minimum)
    used_estimate_range = False
    if total_dec is None:
        er = pricing.get("estimate_range")
        if isinstance(er, dict):
            chosen = er.get("high_usd")
            if chosen is None:
                chosen = er.get("low_usd")

            chosen_dec = _to_decimal(chosen, default=None)

            # ✅ If estimate_range exists but is 0/None, still show a provisional minimum (MVP)
            if chosen_dec is None or chosen_dec == Decimal("0.00"):
                chosen_dec = Decimal("500.00")  # <-- set your minimum here

            total_dec = chosen_dec
            used_estimate_range = True

            # If no items, create 1 provisional item
            if not raw_items:
                qty = None
                if isinstance(vision, dict):
                    qty = vision.get("sqft") or vision.get("count")
                elif (
                    isinstance(vision, list) and vision and isinstance(vision[0], dict)
                ):
                    qty = vision[0].get("sqft") or vision[0].get("count")

                try:
                    qty_f = float(qty) if qty is not None else 1.0
                except Exception:
                    qty_f = 1.0
                if qty_f <= 0:
                    qty_f = 1.0

                raw_items = [
                    {
                        "code": "provisional_estimate",
                        "label": "Interior painting (estimate)",
                        "description": "Provisional estimate (Option 1). Final price after quick review.",
                        "quantity": qty_f,
                        "unit": "sqft" if qty is not None else "job",
                        "category": "labor",
                        "total_usd": str(total_dec),
                        "prep_level": (
                            vision.get("prep_level")
                            if isinstance(vision, dict)
                            else None
                        ),
                        "access_risk": (
                            vision.get("access_risk")
                            if isinstance(vision, dict)
                            else None
                        ),
                    }
                ]

    # 5) labor/materials
    labor_usd = _pick_first(pricing, ["labor_usd", "labor", "labor_total_usd"])
    materials_usd = _pick_first(
        pricing, ["materials_usd", "materials", "materials_total_usd"]
    )

    labor_dec = _to_decimal(labor_usd, default=Decimal("0.00")) or Decimal("0.00")
    materials_dec = _to_decimal(materials_usd, default=Decimal("0.00")) or Decimal(
        "0.00"
    )

    if labor_dec == Decimal("0.00") and materials_dec == Decimal("0.00"):
        for it in raw_items:
            t = _extract_total_usd(it)
            if t is None:
                continue
            cat = _guess_category(it)
            if cat.startswith("material"):
                materials_dec += t
            else:
                labor_dec += t

    # If we have a total but labor/materials are still 0, set labor = total (simple MVP)
    if (
        total_dec is not None
        and labor_dec == Decimal("0.00")
        and materials_dec == Decimal("0.00")
    ):
        labor_dec = total_dec

    normalized_pricing_output = {
        **pricing,
        "labor_usd": str(labor_dec),
        "materials_usd": str(materials_dec),
        # Persist computed/provisional total as string
        "total_usd": str(total_dec) if total_dec is not None else None,
    }

    project = {
        "estimate_id": f"lead_{getattr(lead, 'id', '')}",
        "date": today.isoformat(),
        "valid_until": (today + timedelta(days=30)).isoformat(),
    }

    out = build_pricing_output_from_legacy(
        pricing_output=normalized_pricing_output,
        items=raw_items,
        project=project,
    )

    # Optional: add a note if we used estimate_range (if schema allows notes)
    try:
        if (
            used_estimate_range
            and hasattr(out, "notes")
            and isinstance(out.notes, list)
        ):
            out.notes.append(
                "Estimate shown (Option 1): derived from estimate_range. Final price pending review."
            )
    except Exception:
        pass

    if hasattr(out, "model_dump"):
        return out.model_dump()
    if hasattr(out, "dict"):
        return out.dict()
    return {"meta": {}, "line_items": [], "subtotals": {}, "totals": {}}

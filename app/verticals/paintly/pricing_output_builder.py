from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from app.verticals.paintly.pricing_output_schema import (
    PricingLineItem,
    PricingMeta,
    PricingOutput,
    PricingSubtotals,
    PricingTotals,
)

MONEY_Q = Decimal("0.01")


# -------------------------
# Helpers
# -------------------------
def _val(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _money(val: Any, default: Decimal = Decimal("0.00")) -> Decimal:
    d = _to_decimal(val, default=default)
    if d is None:
        d = default
    return d.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _to_decimal(
    val: Any, default: Optional[Decimal] = Decimal("0.00")
) -> Optional[Decimal]:
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
    for k in [
        "quantity",
        "qty",
        "sqft",
        "square_feet",
        "area_sqft",
        "count",
        "units",
        "sqm",
        "area_sqm",
    ]:
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


def _extract_total_eur(it: Any) -> Optional[Decimal]:
    for k in [
        "total_EUR",
        "line_total_EUR",
        "amount_EUR",
        "base_total_EUR",
        "total_incl_vat",
        "grand_total",
        "total",
        "amount",
        "total_eur",
    ]:
        v = _val(it, k)
        if v is None:
            continue
        dec = _to_decimal(v, default=Decimal("0.00"))
        if dec and dec != Decimal("0.00"):
            return dec

    unit_price = (
        _val(it, "unit_price") or _val(it, "unit_price_eur") or _val(it, "price_eur")
    )
    qty = _extract_qty(it)
    if unit_price is not None and qty > 0:
        up = _to_decimal(unit_price, default=Decimal("0.00"))
        if up and up != Decimal("0.00"):
            return up * (_to_decimal(qty, default=Decimal("0.00")) or Decimal("0.00"))

    return None


def _extract_total_EUR(it: Any) -> Optional[Decimal]:
    return _extract_total_eur(it)


def _coerce_pricing_dict(pricing: Any) -> Dict[str, Any]:
    if pricing is None:
        return {}
    if isinstance(pricing, dict):
        return pricing
    data = getattr(pricing, "data", None)
    if isinstance(data, dict):
        return data
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


def _lead_area_sqm(lead: Any, vision: Any) -> Optional[float]:
    # 1) lead.square_meters
    try:
        sqm = getattr(lead, "square_meters", None)
        if sqm is not None:
            f = float(sqm)
            if f > 0:
                return f
    except Exception:
        pass

    # 2) lead.intake_payload.square_meters
    try:
        raw = getattr(lead, "intake_payload", None)
        if raw:
            payload = __import__("json").loads(raw)
            if isinstance(payload, dict):
                v = payload.get("square_meters") or payload.get("area_sqm")
                if v is not None:
                    f = float(v)
                    if f > 0:
                        return f
    except Exception:
        pass

    # 3) vision dict/list
    try:
        if isinstance(vision, dict):
            v = vision.get("area_sqm") or vision.get("sqm")
            if v is not None:
                f = float(v)
                if f > 0:
                    return f
        if isinstance(vision, list) and vision and isinstance(vision[0], dict):
            v = vision[0].get("area_sqm") or vision[0].get("sqm")
            if v is not None:
                f = float(v)
                if f > 0:
                    return f
    except Exception:
        pass

    return None


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
        currency="EUR",
    )

    line_items: List[PricingLineItem] = []
    for idx, it in enumerate(items, start=1):
        total_raw = _extract_total_eur(it)
        if total_raw is None:
            continue

        # ✅ ensure money-safe total (2 decimals)
        total_dec = _money(total_raw)

        qty = _extract_qty(it)
        if qty <= 0:
            qty = 1.0

        qty_dec = _to_decimal(qty, default=Decimal("1.00")) or Decimal("1.00")
        if qty_dec == 0:
            qty_dec = Decimal("1.00")

        # ✅ critical: quantize unit_price to money (prevents repeating decimals)
        unit_price = _money(total_dec / qty_dec)

        desc = _val(it, "notes") or _val(it, "description")

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

    # ✅ keep buckets money-safe too
    labor = _money(pricing_output.get("labor_eur"))
    materials = _money(pricing_output.get("materials_eur"))

    pre_tax_amount = _to_decimal(pricing_output.get("total_eur"), default=None)
    if pre_tax_amount is not None:
        pre_tax_amount = _money(pre_tax_amount)

    if pre_tax_amount is None:
        s = Decimal("0.00")
        any_item = False
        for li in line_items:
            if li.total is not None:
                any_item = True
                s += _money(li.total)
        if any_item and s != Decimal("0.00"):
            pre_tax_amount = _money(s)
        else:
            if (labor + materials) != Decimal("0.00"):
                pre_tax_amount = _money(labor + materials)
            else:
                pre_tax_amount = Decimal("0.00")

    # ✅ totals money-safe (even if already quantized, this guarantees schema constraints)
    pre_tax_amount = _money(pre_tax_amount)

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
    MVP:
    - Prefer pricing.total_eur
    - Else sum items
    - Else estimate_range (high/low)
    - Else FINAL fallback: minimum provisional total (so never missing_total)
    """
    today = date.today()
    MIN_PROVISIONAL_TOTAL = Decimal("500.00")  # <-- tweak as you like

    pricing = _coerce_pricing_dict(pricing)

    raw_items = (
        pricing.get("line_items")
        or pricing.get("items")
        or pricing.get("breakdown")
        or pricing.get("rows")
        or []
    )
    raw_items = _as_list(raw_items)

    total_eur = _pick_first(
        pricing, ["total_eur", "grand_total_eur", "grand_total", "total"]
    )
    total_dec: Optional[Decimal] = None
    if total_eur is not None:
        td = _to_decimal(total_eur, default=Decimal("0.00"))
        if td and td != Decimal("0.00"):
            total_dec = td

    # fallback: sum items
    if total_dec is None and raw_items:
        s = Decimal("0.00")
        any_item = False
        for it in raw_items:
            t = _extract_total_eur(it)
            if t is not None:
                any_item = True
                s += t
        if any_item and s != Decimal("0.00"):
            total_dec = s

    # fallback: estimate_range
    used_estimate_range = False
    if total_dec is None:
        er = pricing.get("estimate_range")
        if isinstance(er, dict):
            chosen = er.get("high_eur")
            if chosen is None:
                chosen = er.get("low_eur")

            chosen_dec = _to_decimal(chosen, default=None)
            if chosen_dec is None or chosen_dec == Decimal("0.00"):
                chosen_dec = MIN_PROVISIONAL_TOTAL

            total_dec = chosen_dec
            used_estimate_range = True

            if not raw_items:
                sqm = _lead_area_sqm(lead, vision)
                qty_f = float(sqm) if sqm and sqm > 0 else 1.0
                raw_items = [
                    {
                        "code": "provisional_estimate",
                        "label": "Schilderwerk (indicatie)",
                        "description": "Indicatie op basis van beperkte input. Definitieve prijs na korte review.",
                        "quantity": qty_f,
                        "unit": "sqm" if sqm else "job",
                        "category": "labor",
                        "total_eur": str(total_dec),
                    }
                ]

    # ✅ FINAL fallback: still no total => set minimum provisional
    if total_dec is None:
        total_dec = MIN_PROVISIONAL_TOTAL
        if not raw_items:
            sqm = _lead_area_sqm(lead, vision)
            qty_f = float(sqm) if sqm and sqm > 0 else 1.0
            raw_items = [
                {
                    "code": "provisional_minimum",
                    "label": "Schilderwerk (indicatie)",
                    "description": "Indicatie (minimum) omdat er nog onvoldoende pricing-data is. Definitieve prijs na review.",
                    "quantity": qty_f,
                    "unit": "sqm" if sqm else "job",
                    "category": "labor",
                    "total_eur": str(total_dec),
                }
            ]

    labor_eur = _pick_first(pricing, ["labor_eur", "labor", "labor_total_eur"])
    materials_eur = _pick_first(
        pricing, ["materials_eur", "materials", "materials_total_eur"]
    )

    labor_dec = _to_decimal(labor_eur, default=Decimal("0.00")) or Decimal("0.00")
    materials_dec = _to_decimal(materials_eur, default=Decimal("0.00")) or Decimal(
        "0.00"
    )

    if labor_dec == Decimal("0.00") and materials_dec == Decimal("0.00"):
        for it in raw_items:
            t = _extract_total_eur(it)
            if t is None:
                continue
            cat = _guess_category(it)
            if cat.startswith("material"):
                materials_dec += t
            else:
                labor_dec += t

    if (
        total_dec is not None
        and labor_dec == Decimal("0.00")
        and materials_dec == Decimal("0.00")
    ):
        labor_dec = total_dec

    normalized_pricing_output = {
        **pricing,
        "labor_eur": str(labor_dec),
        "materials_eur": str(materials_dec),
        "total_eur": str(total_dec) if total_dec is not None else None,
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

    try:
        if (
            used_estimate_range
            and hasattr(out, "notes")
            and isinstance(out.notes, list)
        ):
            out.notes.append(
                "Indicatie: afgeleid van estimate_range. Definitieve prijs na korte review."
            )
    except Exception:
        pass

    if hasattr(out, "model_dump"):
        d = out.model_dump()
    elif hasattr(out, "dict"):
        d = out.dict()
    else:
        d = {"meta": {}, "line_items": [], "subtotals": {}, "totals": {}}

    # ✅ Extra compatibility fields (handig voor oudere UI's)
    # Als ergens nog op estimate_json["total_eur"] gekeken wordt, werkt dat ook.
    d["total_eur"] = str(total_dec) if total_dec is not None else None
    d["currency"] = "EUR"

    return d

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from decimal import Decimal, ROUND_HALF_UP

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.verticals.paintly.assumptions import PAINTLY_SCOPE_ASSUMPTIONS
from app.verticals.paintly.copy import PAINTLY_ESTIMATE_COPY, fmt_qty
from app.verticals.paintly.disclaimer import PAINTLY_ESTIMATE_DISCLAIMER
from app.verticals.paintly.item_mapping import map_surfaces_to_items
from app.verticals.paintly.locale_eu import calc_vat, fmt_eur
from app.verticals.paintly.needs_review import PAINTLY_NEEDS_REVIEW_COPY
from app.verticals.paintly.pricing_output_builder import (
    build_pricing_output_from_legacy,
)

TEMPLATE_DIR = Path(__file__).parent / "templates"

DEFAULT_VAT_RATE = 0.21
VALID_DAYS_DEFAULT = 30
PROVISIONAL_MINIMUM_EXCL_VAT = 500.0


def _show_tax(pricing: Any) -> bool:
    """Template helper: show tax block if canonical pricing contains tax info."""
    tax = getattr(pricing, "tax", None)
    if not tax:
        return False
    return (getattr(tax, "tax_amount", None) is not None) or (
        getattr(tax, "tax_rate", None) is not None
    )


def _as_list(val: Any) -> List[str]:
    """Normalize various inputs to a list[str] for template bullets."""
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, tuple):
        return [str(x) for x in val]
    if isinstance(val, str):
        parts = [p.strip() for p in val.splitlines()]
        return [p for p in parts if p]
    return [str(val)]


def _to_float(v: Any, default: float = 0.0) -> float:
    """Best-effort float parsing (supports '€', comma decimals)."""
    if v is None:
        return default
    try:
        return float(v)
    except Exception:
        try:
            s = str(v).strip().replace("€", "").replace(",", ".")
            return float(s)
        except Exception:
            return default


MONEY_Q = Decimal("0.01")


def _d(x: Any) -> Decimal:
    if x is None:
        return Decimal("0.00")
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal("0.00")


def _money_dec(x: Any) -> Decimal:
    return _d(x).quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _sum_canonical_line_items_total(canonical_pricing: Any) -> Decimal:
    s = Decimal("0.00")
    items = getattr(canonical_pricing, "line_items", None) or []
    for it in items:
        s += _money_dec(getattr(it, "total", 0))
    return _money_dec(s)


def _sum_line_items_total_from_pricing_output(pricing_output: Dict[str, Any]) -> float:
    """
    Sum totals from raw pricing_output line items. Accepts a few common key variants.
    NOTE: This is *not* the same as canonical_pricing.line_items.
    """
    items = pricing_output.get("line_items") or pricing_output.get("items") or []
    if not isinstance(items, list):
        return 0.0

    total = 0.0
    for it in items:
        if not isinstance(it, dict):
            continue
        total += _to_float(
            it.get("total_eur")
            or it.get("total")
            or it.get("amount_eur")
            or it.get("amount"),
            0.0,
        )
    return total


def _sum_canonical_line_items_total(canonical_pricing: Any) -> float:
    """
    Sum totals from canonical_pricing.line_items (this matches what estimate.html renders).
    """
    items = getattr(canonical_pricing, "line_items", None)
    if not items:
        return 0.0

    total = 0.0
    for it in items:
        total += _to_float(getattr(it, "total", None), 0.0)
    return total


def _pick_subtotal_excl_vat(
    *, pricing_output: Dict[str, Any], canonical_pricing: Any
) -> float:
    """
    Robust subtotal picker for EU renderer.

    Priority (most reliable first):
      1) canonical_pricing totals/attrs (if present)
      2) sum(canonical_pricing.line_items[*].total)  <-- matches template
      3) pricing_output.totals.pre_tax (dict shape)
      4) explicit subtotal fields on pricing_output
      5) sum(raw pricing_output line_items)
      6) labor + materials (legacy buckets)
      7) 0.0
    """
    # 1) canonical pricing totals/attrs
    for attr in ("subtotal_excl_vat", "subtotal", "pre_tax", "pre_tax_eur"):
        f = _to_float(getattr(canonical_pricing, attr, None), 0.0)
        if f > 0:
            return f

    totals_obj = getattr(canonical_pricing, "totals", None)
    if totals_obj:
        for attr in ("pre_tax", "pre_tax_eur", "subtotal_excl_vat", "subtotal"):
            f = _to_float(getattr(totals_obj, attr, None), 0.0)
            if f > 0:
                return f

    # 2) canonical line-items sum (most consistent with UI)
    canonical_sum = _sum_canonical_line_items_total(canonical_pricing)
    if canonical_sum > 0:
        return canonical_sum

    # 3) schema-style nested totals in pricing_output (dict)
    totals = pricing_output.get("totals")
    if isinstance(totals, dict):
        for k in ("pre_tax", "pre_tax_eur", "subtotal_excl_vat", "subtotal"):
            f = _to_float(totals.get(k), 0.0)
            if f > 0:
                return f

    # 4) explicit subtotal fields on pricing_output
    for k in ("subtotal_excl_vat_eur", "subtotal_excl_vat", "subtotal"):
        f = _to_float(pricing_output.get(k), 0.0)
        if f > 0:
            return f

    # 5) raw line-items sum
    raw_sum = _sum_line_items_total_from_pricing_output(pricing_output)
    if raw_sum > 0:
        return raw_sum

    # 6) last resort: labor + materials buckets
    labor = _to_float(
        pricing_output.get("labor_eur") or pricing_output.get("labor"), 0.0
    )
    materials = _to_float(
        pricing_output.get("materials_eur") or pricing_output.get("materials"), 0.0
    )
    if (labor + materials) > 0:
        return labor + materials

    return 0.0


def _pick_vat_rate(pricing_output: Dict[str, Any]) -> float:
    """
    VAT rate selection:
      - pricing_output["vat_rate"] (preferred)
      - pricing_output["tax_rate"]
      - DEFAULT_VAT_RATE
    """
    vat_rate = pricing_output.get("vat_rate")
    if vat_rate is None and pricing_output.get("tax_rate") is not None:
        vat_rate = pricing_output.get("tax_rate")
    return _to_float(vat_rate, DEFAULT_VAT_RATE)


def _jinja_env() -> Environment:
    """Create a Jinja environment for templates."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.globals["fmt_eur"] = fmt_eur
    env.globals["fmt_qty"] = fmt_qty
    return env


def render_estimate_html_v1(
    *,
    vision_output: Dict[str, Any],
    pricing_output: Dict[str, Any],
    project: Dict[str, Any],
    company: Dict[str, Any],
    # optional extras used by template
    lead: Optional[Dict[str, Any]] = None,
    customer: Optional[Dict[str, Any]] = None,
    token: Optional[str] = None,
) -> str:
    """
    Rendered HTML for Paintly (EU-first).

    Expects:
      - vision_output contains "surfaces": list[dict]
      - pricing_output contains totals and optionally per-surface items
    """
    pricing_ready = bool(pricing_output.get("pricing_ready", True))

    # Build line items (mapping may still accept legacy sqft keys; EU cleanup can come later)
    items = map_surfaces_to_items(
        surfaces=vision_output.get("surfaces", []) or [],
        pricing=pricing_output,
    )

    today = date.today()
    proj = {
        "location": project.get("location", "—"),
        "estimate_id": project.get("estimate_id")
        or f"EST-{project.get('lead_id', '—')}",
        "lead_id": project.get("lead_id"),
        "date": project.get("date", today.isoformat()),
        "valid_until": project.get(
            "valid_until", (today + timedelta(days=VALID_DAYS_DEFAULT)).isoformat()
        ),
        # optional fields used by template if present
        "square_meters": project.get("square_meters"),
        "description": project.get("description"),
    }

    # Normalize into canonical schema used by template
    canonical_pricing = build_pricing_output_from_legacy(
        pricing_output=pricing_output,
        items=items,
        project=proj,
    )

    # --- Copy blocks ---
    validity_copy = PAINTLY_ESTIMATE_COPY.validity_copy.format(days=VALID_DAYS_DEFAULT)
    subject_to_verification_copy = PAINTLY_ESTIMATE_COPY.subject_to_verification_copy

    scope_bullets = getattr(PAINTLY_SCOPE_ASSUMPTIONS, "included", None) or project.get(
        "scope_bullets"
    )
    scope_bullets = _as_list(scope_bullets) or [
        "Voorbereiding van oppervlakken waar nodig (schuren/pleisteren/primer op reparaties).",
        "Aanbrengen van afwerklagen op alleen de genoemde oppervlakken.",
        "Standaard afplakken/beschermen en oplever-schoonmaak.",
    ]

    exclusions = _as_list(getattr(PAINTLY_ESTIMATE_DISCLAIMER, "bullets", None))

    # ---- VAT totals (robust) ----
    subtotal_excl_vat = _pick_subtotal_excl_vat(
        pricing_output=pricing_output,
        canonical_pricing=canonical_pricing,
    )

    # ---- VAT totals (bulletproof) ----
    # Subtotal from canonical line-items (exactly what the UI renders)
    subtotal_excl_vat_dec = _sum_canonical_line_items_total(canonical_pricing)

    # Fallback to picked subtotal (from pricing_output/canonical totals)
    if subtotal_excl_vat_dec <= 0:
        subtotal_excl_vat_dec = _money_dec(subtotal_excl_vat)

    # Keep your "minimum provisional" behaviour
    if subtotal_excl_vat_dec <= 0:
        subtotal_excl_vat_dec = _money_dec(PROVISIONAL_MINIMUM_EXCL_VAT)

        print(
            "DEBUG canonical subtotal:",
            subtotal_excl_vat_dec,
            "picked subtotal:",
            subtotal_excl_vat,
            "vat_rate:",
            vat_rate,
        )

    vat_rate = _pick_vat_rate(pricing_output)  # float
    vat_rate_dec = _d(vat_rate)

    vat_amount_dec = _money_dec(subtotal_excl_vat_dec * vat_rate_dec)
    total_incl_vat_dec = _money_dec(subtotal_excl_vat_dec + vat_amount_dec)

    vat = {
        "subtotal_excl_vat": float(subtotal_excl_vat_dec),
        "vat_rate": float(vat_rate_dec),
        "vat_amount": float(vat_amount_dec),
        "total_incl_vat": float(total_incl_vat_dec),
    }

    # Optional breakdown buckets if present (ensure numeric)
    pricing_labor = _to_float(
        pricing_output.get("labor_eur") or pricing_output.get("labor"), 0.0
    )
    pricing_materials = _to_float(
        pricing_output.get("materials_eur") or pricing_output.get("materials"), 0.0
    )

    tmpl = _jinja_env().get_template("estimate.html")
    html = tmpl.render(
        pricing_ready=pricing_ready,
        items=items,
        scope_bullets=scope_bullets,
        exclusions=exclusions,
        pricing_labor=pricing_labor,
        pricing_materials=pricing_materials,
        pricing=canonical_pricing,
        vat=vat,
        show_tax=_show_tax(canonical_pricing),
        validity_copy=validity_copy,
        subject_to_verification_copy=subject_to_verification_copy,
        copy=PAINTLY_ESTIMATE_COPY,
        needs_review=PAINTLY_NEEDS_REVIEW_COPY,
        project=proj,
        company=company,
        lead=lead or {},
        customer=customer or {},
        token=token,
    )

    # Guard: avoid serving unrendered template content
    if "{{" in html or "{%" in html:
        raise RuntimeError(
            "Estimate HTML still contains Jinja tags. "
            "Likely opening template file directly or serving a cached/unrendered object."
        )

    return html


# -------------------------
# Pipeline compatibility wrapper
# -------------------------
def render_estimate_html(estimate: Dict[str, Any]) -> str:
    """Pipeline expects: render_estimate_html(estimate_dict) -> html str"""
    vision_output = (
        estimate.get("vision_output")
        or estimate.get("vision")
        or {"surfaces": estimate.get("surfaces", []) or []}
    )

    pricing_output = (
        estimate.get("pricing_output")
        or estimate.get("pricing")
        or estimate.get("pricing_result")
        or {}
    )

    project = estimate.get("project") or {
        "lead_id": estimate.get("lead_id") or (estimate.get("lead") or {}).get("id"),
        "estimate_id": estimate.get("estimate_id"),
        "location": estimate.get("location"),
        "date": estimate.get("date"),
        "valid_until": estimate.get("valid_until"),
        "scope_bullets": estimate.get("scope_bullets"),
        "square_meters": estimate.get("square_meters"),
        "description": estimate.get("description"),
    }

    company = estimate.get("company") or estimate.get("tenant") or {}

    lead = estimate.get("lead") or {}
    customer = estimate.get("customer") or {}
    token = estimate.get("token")

    return render_estimate_html_v1(
        vision_output=vision_output,
        pricing_output=pricing_output,
        project=project,
        company=company,
        lead=lead,
        customer=customer,
        token=token,
    )

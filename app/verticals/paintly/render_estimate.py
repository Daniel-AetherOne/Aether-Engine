from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.verticals.paintly.pricing_output_builder import (
    build_pricing_output_from_legacy,
)
from app.verticals.paintly.copy import PAINTLY_ESTIMATE_COPY, fmt_qty
from app.verticals.paintly.item_mapping import map_surfaces_to_items
from app.verticals.paintly.assumptions import PAINTLY_SCOPE_ASSUMPTIONS
from app.verticals.paintly.disclaimer import PAINTLY_ESTIMATE_DISCLAIMER
from app.verticals.paintly.needs_review import PAINTLY_NEEDS_REVIEW_COPY
from app.verticals.paintly.locale_eu import fmt_eur, calc_vat

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _show_tax(pricing) -> bool:
    """
    Legacy helper: canonical_pricing may contain tax fields.
    We still expose this for templates that conditionally show tax blocks.
    """
    tax = getattr(pricing, "tax", None)
    if not tax:
        return False
    return (getattr(tax, "tax_amount", None) is not None) or (
        getattr(tax, "tax_rate", None) is not None
    )


def _as_list(val: Any) -> List[str]:
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


def _pick_total_excl_vat(pricing_output: Dict[str, Any]) -> float:
    """
    Robust total picker for EU renderer.
    We accept different shapes:
      - legacy dicts: total_eur/total/subtotal
      - schema dicts: totals.pre_tax / totals.grand_total
      - fallback: labor + materials
    """
    # 1) explicit subtotal fields
    for k in ("subtotal_excl_vat", "subtotal"):
        if pricing_output.get(k) is not None:
            f = _to_float(pricing_output.get(k), 0.0)
            if f > 0:
                return f

    # 2) common total fields (legacy)
    for k in ("total_eur", "total", "grand_total", "grand_total_eur"):
        if pricing_output.get(k) is not None:
            f = _to_float(pricing_output.get(k), 0.0)
            if f > 0:
                return f

    # 3) schema-style nested totals
    totals = pricing_output.get("totals")
    if isinstance(totals, dict):
        for k in ("pre_tax", "grand_total"):
            if totals.get(k) is not None:
                f = _to_float(totals.get(k), 0.0)
                if f > 0:
                    return f

    # 4) last resort: labor + materials
    labor = _to_float(
        pricing_output.get("labor_eur") or pricing_output.get("labor"), 0.0
    )
    materials = _to_float(
        pricing_output.get("materials_eur") or pricing_output.get("materials"), 0.0
    )
    if (labor + materials) > 0:
        return labor + materials

    return 0.0


def render_estimate_html_v1(
    *,
    vision_output: Dict[str, Any],
    pricing_output: Dict[str, Any],
    project: Dict[str, Any],
    company: Dict[str, Any],
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
            "valid_until", (today + timedelta(days=30)).isoformat()
        ),
    }

    # Normalize into canonical schema used by template
    canonical_pricing = build_pricing_output_from_legacy(
        pricing_output=pricing_output,
        items=items,
        project=proj,
    )

    # --- Footer / legal copy ---
    VALID_DAYS = 30
    validity_copy = PAINTLY_ESTIMATE_COPY.validity_copy.format(days=VALID_DAYS)
    subject_to_verification_copy = PAINTLY_ESTIMATE_COPY.subject_to_verification_copy

    # Scope bullets: prefer assumptions.included → project fallback → default list
    scope_bullets = getattr(PAINTLY_SCOPE_ASSUMPTIONS, "included", None) or project.get(
        "scope_bullets"
    )
    scope_bullets = _as_list(scope_bullets) or [
        "Voorbereiding van oppervlakken waar nodig (schuren/pleisteren/primer op reparaties).",
        "Aanbrengen van afwerklagen op alleen de genoemde oppervlakken.",
        "Standaard afplakken/beschermen en oplever-schoonmaak.",
    ]

    # Exclusions: prefer disclaimer bullets → empty list
    exclusions = _as_list(getattr(PAINTLY_ESTIMATE_DISCLAIMER, "bullets", None))

    # ---- EU VAT totals ----
    subtotal_excl_vat = _pick_total_excl_vat(pricing_output)

    vat_rate = (
        pricing_output.get("vat_rate")
        or (
            pricing_output.get("tax_rate")
            if pricing_output.get("tax_rate") is not None
            else None
        )
        or 0.09  # NL default for now; later: derive from lead.country
    )
    vat_rate_f = _to_float(vat_rate, 0.09)

    vat_calc = calc_vat(subtotal_excl_vat=subtotal_excl_vat, vat_rate=vat_rate_f)
    vat = {
        "subtotal_excl_vat": _to_float(
            vat_calc.get("subtotal_excl_vat", subtotal_excl_vat), subtotal_excl_vat
        ),
        "vat_rate": _to_float(vat_calc.get("vat_rate", vat_rate_f), vat_rate_f),
        "vat_amount": _to_float(
            vat_calc.get("vat_amount", vat_calc.get("amount", 0.0)), 0.0
        ),
        "total_incl_vat": _to_float(
            vat_calc.get("total_incl_vat", vat_calc.get("total", 0.0)), 0.0
        ),
    }

    # Optional breakdown buckets if present (ensure numeric)
    pricing_labor = _to_float(
        pricing_output.get("labor_eur") or pricing_output.get("labor"), 0.0
    )
    pricing_materials = _to_float(
        pricing_output.get("materials_eur") or pricing_output.get("materials"), 0.0
    )

    # Jinja env
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )

    # Expose formatters to Jinja
    env.globals["fmt_eur"] = fmt_eur
    env.globals["fmt_qty"] = fmt_qty

    tmpl = env.get_template("estimate.html")

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
    )

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
    """
    Pipeline expects: render_estimate_html(estimate_dict) -> html str
    """
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
    }

    company = estimate.get("company") or estimate.get("tenant") or {}

    return render_estimate_html_v1(
        vision_output=vision_output,
        pricing_output=pricing_output,
        project=project,
        company=company,
    )

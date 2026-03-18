# app/verticals/paintly/render_estimate.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from decimal import Decimal, ROUND_HALF_UP

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.verticals.paintly.assumptions import PAINTLY_SCOPE_ASSUMPTIONS
from app.verticals.paintly.copy import PAINTLY_ESTIMATE_COPY, fmt_qty
from app.verticals.paintly.disclaimer import PAINTLY_ESTIMATE_DISCLAIMER
from app.verticals.paintly.locale_eu import fmt_eur
from app.verticals.paintly.needs_review import PAINTLY_NEEDS_REVIEW_COPY

TEMPLATE_DIR = Path(__file__).parent / "templates"
DEFAULT_VAT_RATE = 0.21
PROVISIONAL_MINIMUM_EXCL_VAT = Decimal("500.00")
MONEY_Q = Decimal("0.01")


def _d(x: Any) -> Decimal:
    if x is None:
        return Decimal("0.00")
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal("0.00")


def _money(x: Any) -> Decimal:
    return _d(x).quantize(MONEY_Q, rounding=ROUND_HALF_UP)


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


def _jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    # template uses fmt_eur + fmt_qty
    env.globals["fmt_eur"] = fmt_eur
    env.globals["fmt_qty"] = fmt_qty
    return env


def _pick_vat_rate(pricing: Dict[str, Any]) -> Decimal:
    # allow override later via pricing["vat_rate"] or pricing["tax_rate"]
    v = pricing.get("vat_rate")
    if v is None:
        v = pricing.get("tax_rate")
    if v is None:
        v = DEFAULT_VAT_RATE
    return _d(v)


def _calc_vat(pricing: Dict[str, Any]) -> Dict[str, float]:
    """
    Your estimate_json already contains:
      totals.pre_tax
      totals.grand_total (usually same for now)
    We compute VAT from totals.pre_tax (excl btw).
    """
    totals = pricing.get("totals") if isinstance(pricing.get("totals"), dict) else {}
    pre_tax = totals.get("pre_tax")

    subtotal_excl = _money(pre_tax)

    # bulletproof fallback
    if subtotal_excl <= 0:
        subtotal_excl = PROVISIONAL_MINIMUM_EXCL_VAT

    vat_rate = _pick_vat_rate(pricing)
    vat_amount = _money(subtotal_excl * vat_rate)
    total_incl = _money(subtotal_excl + vat_amount)

    return {
        "subtotal_excl_vat": float(subtotal_excl),
        "vat_rate": float(vat_rate),
        "vat_amount": float(vat_amount),
        "total_incl_vat": float(total_incl),
    }


def render_estimate_html_v2(
    *,
    pricing: Dict[str, Any],
    project: Dict[str, Any],
    company: Dict[str, Any],
    lead: Optional[Dict[str, Any]] = None,
    customer: Optional[Dict[str, Any]] = None,
    token: Optional[str] = None,
) -> str:
    pricing = pricing or {}

    # pricing_ready: treat as ready unless explicitly flagged for review
    meta = pricing.get("meta") if isinstance(pricing.get("meta"), dict) else {}

    # NEW canonical fields (from pricing_engine patch)
    needs_review_flag = bool(pricing.get("needs_review", False))

    review_reasons = pricing.get("review_reasons")
    if review_reasons is None:
        # backwards compat (older meta key)
        review_reasons = (
            meta.get("needs_review_reasons") or meta.get("review_reasons") or []
        )
    if isinstance(review_reasons, str):
        review_reasons = [review_reasons]
    elif not isinstance(review_reasons, list):
        review_reasons = [str(review_reasons)]

    # ensure list[str]
    review_reasons = [str(x) for x in review_reasons if x is not None]

    pricing_ready = (not needs_review_flag) and (len(review_reasons) == 0)

    # scope + exclusions blocks
    scope_bullets = _as_list(getattr(PAINTLY_SCOPE_ASSUMPTIONS, "included", None))
    if not scope_bullets:
        scope_bullets = [
            "Voorbereiding van oppervlakken waar nodig (licht schuren/bijwerken).",
            "Aanbrengen van afwerklagen op de genoemde oppervlakken.",
            "Standaard afplakken/beschermen en oplever-schoonmaak.",
        ]

    exclusions = _as_list(getattr(PAINTLY_ESTIMATE_DISCLAIMER, "bullets", None))

    # buckets shown in sidebar
    subtotals = (
        pricing.get("subtotals") if isinstance(pricing.get("subtotals"), dict) else {}
    )
    pricing_labor = float(_money(subtotals.get("labor")))
    pricing_materials = float(_money(subtotals.get("materials")))

    # Explainability (Step B)
    decision_vars = pricing.get("decision_vars")
    if decision_vars is None and isinstance(meta.get("decision_vars"), dict):
        decision_vars = meta.get("decision_vars")

    # Optional: for template: show on sidebar or "Assumptions"
    assumptions_ctx = {
        "prep_level": (decision_vars or {}).get("prep_level"),
        "complexity_level": (decision_vars or {}).get("complexity_level"),
        "access_risk": (decision_vars or {}).get("access_risk"),
        "review_reasons": review_reasons,
        "needs_review": needs_review_flag,
    }

    # If an explicit override_total_incl_vat is present in meta, recompute VAT from that.
    override_total = None
    try:
        if isinstance(meta, dict) and meta.get("override_total_incl_vat") is not None:
            override_total = _money(meta.get("override_total_incl_vat"))
    except Exception:
        override_total = None

    if override_total is not None and override_total > 0:
        # Reverse-calc VAT components from override_total
        vat_rate = _pick_vat_rate(pricing)
        one_plus = Decimal("1") + vat_rate
        subtotal_excl = (override_total / one_plus).quantize(MONEY_Q, rounding=ROUND_HALF_UP)
        vat_amount = (override_total - subtotal_excl).quantize(MONEY_Q, rounding=ROUND_HALF_UP)
        vat = {
            "subtotal_excl_vat": float(subtotal_excl),
            "vat_rate": float(vat_rate),
            "vat_amount": float(vat_amount),
            "total_incl_vat": float(override_total),
        }
    else:
        vat = _calc_vat(pricing)

    # Debug: log final pricing/meta/vat snapshot before templating
    try:
        from app.verticals.paintly.router_app import logger as paintly_logger  # type: ignore
    except Exception:
        paintly_logger = None

    if paintly_logger:
        try:
            paintly_logger.info(
                "RENDER_ESTIMATE_HTML_V2_SNAPSHOT totals=%r meta=%r vat=%r",
                pricing.get("totals"),
                meta,
                vat,
            )
        except Exception:
            pass

    tmpl = _jinja_env().get_template("estimate.html")
    html = tmpl.render(
        pricing_ready=pricing_ready,
        pricing=pricing,  # template uses pricing.line_items, pricing.meta, pricing.subtotals, pricing.totals
        vat=vat,
        pricing_labor=pricing_labor,
        pricing_materials=pricing_materials,
        copy=PAINTLY_ESTIMATE_COPY,
        needs_review=PAINTLY_NEEDS_REVIEW_COPY,
        scope_bullets=scope_bullets,
        exclusions=exclusions,
        project=project,
        company=company,
        lead=lead or {},
        customer=customer or {},
        token=token,
        needs_review_flag=needs_review_flag,
        review_reasons=review_reasons,
        decision_vars=decision_vars or {},
        assumptions_ctx=assumptions_ctx,
    )

    # Guard: avoid serving unrendered template content
    if "{{" in html or "{%" in html:
        raise RuntimeError("Estimate HTML still contains Jinja tags.")
    return html


# -------------------------
# Pipeline compatibility wrapper
# -------------------------
def render_estimate_html(estimate: Dict[str, Any]) -> str:
    """
    Pipeline calls: render_estimate_html(estimate_json_dict) -> html
    Here `estimate` is already your canonical pricing output schema dict.
    """
    estimate = estimate or {}
    if not isinstance(estimate, dict):
        raise TypeError("estimate must be dict")

    pricing = estimate  # <-- key change: template reads pricing.* directly

    meta = pricing.get("meta") if isinstance(pricing.get("meta"), dict) else {}

    project = {
        "lead_id": meta.get("estimate_id"),
        "estimate_id": meta.get("estimate_id"),
        "location": estimate.get("location") or "—",
        "date": meta.get("date"),
        "valid_until": meta.get("valid_until"),
        "square_meters": meta.get("area_m2") or estimate.get("square_meters"),
        "description": estimate.get("description"),
    }

    company = estimate.get("company") or estimate.get("tenant") or {}
    lead = estimate.get("lead") or {}
    customer = estimate.get("customer") or {}
    token = estimate.get("token")

    return render_estimate_html_v2(
        pricing=pricing,
        project=project,
        company=company,
        lead=lead,
        customer=customer,
        token=token,
    )


def render_estimate_pdf_html(estimate: Dict[str, Any]) -> str:
    """
    Dedicated PDF-friendly HTML renderer for WeasyPrint.

    Uses a simpler, document-style template (estimate_pdf.html) instead of the
    web-optimized dashboard template.
    """
    estimate = estimate or {}
    if not isinstance(estimate, dict):
        raise TypeError("estimate must be dict")

    pricing = estimate
    meta = pricing.get("meta") if isinstance(pricing.get("meta"), dict) else {}

    project = {
        "lead_id": meta.get("estimate_id"),
        "estimate_id": meta.get("estimate_id"),
        "location": estimate.get("location") or "—",
        "date": meta.get("date"),
        "valid_until": meta.get("valid_until"),
        "square_meters": meta.get("area_m2") or estimate.get("square_meters"),
        "description": estimate.get("description"),
        "address": estimate.get("address") or meta.get("address"),
    }

    company = estimate.get("company") or estimate.get("tenant") or {}
    lead = estimate.get("lead") or {}
    customer = estimate.get("customer") or {}
    token = estimate.get("token")

    pricing = pricing or {}
    pdf_pricing = pricing  # reuse existing helpers

    # Reuse existing computation helpers from render_estimate_html_v2
    meta = pdf_pricing.get("meta") if isinstance(pdf_pricing.get("meta"), dict) else {}
    needs_review_flag = bool(pdf_pricing.get("needs_review", False))
    review_reasons = pdf_pricing.get("review_reasons")
    if review_reasons is None:
        review_reasons = (
            meta.get("needs_review_reasons") or meta.get("review_reasons") or []
        )
    if isinstance(review_reasons, str):
        review_reasons = [review_reasons]
    elif not isinstance(review_reasons, list):
        review_reasons = [str(review_reasons)]
    review_reasons = [str(x) for x in review_reasons if x is not None]
    pricing_ready = (not needs_review_flag) and (len(review_reasons) == 0)

    scope_bullets = _as_list(getattr(PAINTLY_SCOPE_ASSUMPTIONS, "included", None))
    if not scope_bullets:
        scope_bullets = [
            "Voorbereiding van oppervlakken waar nodig (licht schuren/bijwerken).",
            "Aanbrengen van afwerklagen op de genoemde oppervlakken.",
            "Standaard afplakken/beschermen en oplever-schoonmaak.",
        ]

    exclusions = _as_list(getattr(PAINTLY_ESTIMATE_DISCLAIMER, "bullets", None))

    subtotals = (
        pdf_pricing.get("subtotals")
        if isinstance(pdf_pricing.get("subtotals"), dict)
        else {}
    )
    pricing_labor = float(_money(subtotals.get("labor")))
    pricing_materials = float(_money(subtotals.get("materials")))

    decision_vars = pdf_pricing.get("decision_vars")
    if decision_vars is None and isinstance(meta.get("decision_vars"), dict):
        decision_vars = meta.get("decision_vars")

    assumptions_ctx = {
        "prep_level": (decision_vars or {}).get("prep_level"),
        "complexity_level": (decision_vars or {}).get("complexity_level"),
        "access_risk": (decision_vars or {}).get("access_risk"),
        "review_reasons": review_reasons,
        "needs_review": needs_review_flag,
    }

    override_total = None
    try:
        if isinstance(meta, dict) and meta.get("override_total_incl_vat") is not None:
            override_total = _money(meta.get("override_total_incl_vat"))
    except Exception:
        override_total = None

    if override_total is not None and override_total > 0:
        vat_rate = _pick_vat_rate(pdf_pricing)
        one_plus = Decimal("1") + vat_rate
        subtotal_excl = (override_total / one_plus).quantize(
            MONEY_Q, rounding=ROUND_HALF_UP
        )
        vat_amount = (override_total - subtotal_excl).quantize(
            MONEY_Q, rounding=ROUND_HALF_UP
        )
        vat = {
            "subtotal_excl_vat": float(subtotal_excl),
            "vat_rate": float(vat_rate),
            "vat_amount": float(vat_amount),
            "total_incl_vat": float(override_total),
        }
    else:
        vat = _calc_vat(pdf_pricing)

    tmpl = _jinja_env().get_template("estimate_pdf.html")
    html = tmpl.render(
        pricing_ready=pricing_ready,
        pricing=pdf_pricing,
        vat=vat,
        pricing_labor=pricing_labor,
        pricing_materials=pricing_materials,
        copy=PAINTLY_ESTIMATE_COPY,
        needs_review=PAINTLY_NEEDS_REVIEW_COPY,
        scope_bullets=scope_bullets,
        exclusions=exclusions,
        project=project,
        company=company,
        lead=lead or {},
        customer=customer or {},
        token=token,
        needs_review_flag=needs_review_flag,
        review_reasons=review_reasons,
        decision_vars=decision_vars or {},
        assumptions_ctx=assumptions_ctx,
    )

    if "{{" in html or "{%" in html:
        raise RuntimeError("Estimate PDF HTML still contains Jinja tags.")
    return html

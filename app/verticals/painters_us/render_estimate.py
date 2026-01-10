from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List
from app.verticals.painters_us.pricing_output_builder import (
    build_pricing_output_from_legacy,
)


from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.verticals.painters_us.copy import (
    US_PAINTERS_ESTIMATE_COPY,
    fmt_usd,
    fmt_usd_range,
    fmt_qty,
)


from app.verticals.painters_us.item_mapping import map_surfaces_to_items
from app.verticals.painters_us.assumptions import US_PAINTERS_SCOPE_ASSUMPTIONS
from app.verticals.painters_us.disclaimer import US_PAINTERS_ESTIMATE_DISCLAIMER
from app.verticals.painters_us.needs_review import US_PAINTERS_NEEDS_REVIEW_COPY


TEMPLATE_DIR = Path(__file__).parent / "templates"


def _show_tax(pricing) -> bool:
    tax = getattr(pricing, "tax", None)
    if not tax:
        return False
    return (tax.tax_amount is not None) or (tax.tax_rate is not None)


def _as_list(val: Any) -> List[str]:
    if val is None:
        return []
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, tuple):
        return [str(x) for x in val]
    if isinstance(val, str):
        # allow newline-separated strings
        parts = [p.strip() for p in val.splitlines()]
        return [p for p in parts if p]
    return [str(val)]


def render_us_estimate_html(
    *,
    vision_output: Dict[str, Any],
    pricing_output: Dict[str, Any],
    project: Dict[str, Any],
    company: Dict[str, Any],
) -> str:
    """
    Returns rendered HTML for US Painters estimate.

    Expects:
      - vision_output contains "surfaces": list[dict]
      - pricing_output contains totals and optionally per-surface items
    """

    pricing_ready = bool(pricing_output.get("pricing_ready", True))

    # Build line items (your mapping already handles sqft etc)
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

    canonical_pricing = build_pricing_output_from_legacy(
        pricing_output=pricing_output,
        items=items,
        project=proj,
    )

    # --- Footer / legal readiness (10.5.5) ---
    VALID_DAYS = 30
    validity_copy = US_PAINTERS_ESTIMATE_COPY.validity_copy.format(days=VALID_DAYS)

    subject_to_verification_copy = (
        US_PAINTERS_ESTIMATE_COPY.subject_to_verification_copy
    )

    # Scope bullets: prefer assumptions if it contains bullets, else project fallback
    # Scope bullets: prefer assumptions.included → project fallback → default list
    scope_bullets = getattr(
        US_PAINTERS_SCOPE_ASSUMPTIONS, "included", None
    ) or project.get("scope_bullets")

    scope_bullets = _as_list(scope_bullets) or [
        "Surface preparation as needed (scrape/sand/patch) and priming of repaired areas.",
        "Application of finish coats to listed surfaces only.",
        "Standard protection (masking/drop cloths) and cleanup.",
    ]

    # Exclusions: prefer disclaimer bullets → empty list
    exclusions = getattr(US_PAINTERS_ESTIMATE_DISCLAIMER, "bullets", None)
    exclusions = _as_list(exclusions)

    # Normalize pricing
    pricing_labor_usd = pricing_output.get("labor_usd", 0) or 0
    pricing_materials_usd = pricing_output.get("materials_usd", 0) or 0
    pricing_total_usd = pricing_output.get("total_usd", None)

    # Jinja env
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )

    # Expose formatters to Jinja
    env.globals["fmt_usd"] = fmt_usd
    env.globals["fmt_usd_range"] = fmt_usd_range
    env.globals["fmt_qty"] = fmt_qty

    tmpl = env.get_template("estimate.html")

    html = tmpl.render(
        pricing_ready=pricing_ready,
        items=items,
        scope_bullets=scope_bullets,
        exclusions=exclusions,
        pricing_labor_usd=pricing_labor_usd,
        pricing_materials_usd=pricing_materials_usd,
        pricing_total_usd=pricing_total_usd,
        pricing=canonical_pricing,
        show_tax=_show_tax(canonical_pricing),
        validity_copy=validity_copy,
        subject_to_verification_copy=subject_to_verification_copy,
        copy=US_PAINTERS_ESTIMATE_COPY,
        needs_review=US_PAINTERS_NEEDS_REVIEW_COPY,
        project=proj,
        company=company,
    )

    # Sanity check: if braces remain, you're not looking at rendered output (or template is wrong)
    if "{{" in html or "{%" in html:
        raise RuntimeError(
            "Estimate HTML still contains Jinja tags. "
            "Likely opening template file directly or serving a cached/unrendered object."
        )

    return html

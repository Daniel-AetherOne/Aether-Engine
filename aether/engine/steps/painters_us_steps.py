from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from aether.engine.context import PipelineState, StepResult
from aether.engine.config import StepConfig

from app.models import Lead
from app.services.storage import get_storage
from app.tasks.vision_task import run_vision_for_lead

from app.verticals.painters_us.vision_aggregate_us import (
    aggregate_images_to_surfaces as aggregate_vision,
)
from app.verticals.painters_us.pricing_engine_us import run_pricing_engine
from app.verticals.painters_us.pricing_output_builder import build_pricing_output
from app.verticals.painters_us.needs_review import needs_review_from_output


def _ensure_obj(x: Any) -> Any:
    """
    If a stage accidentally returns JSON as a string, parse it back to dict/list.
    Keeps non-JSON strings untouched.
    """
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return x
    return x


# -------------------------
# Defaults for template context (1.5.5)
# -------------------------
def _default_company() -> Dict[str, Any]:
    return {"name": "Paintly", "phone": "", "email": ""}


def _default_copy() -> Dict[str, Any]:
    return {
        "doc_title": "Painting Estimate",
        "scope_label": "Scope",
        "exclusions_label": "Exclusions",
        "labor_label": "Labor",
        "materials_label": "Materials",
    }


def _default_scope_bullets() -> List[str]:
    return [
        "Protect floors and nearby surfaces",
        "Standard prep (light sanding where needed)",
        "Two-coat application where applicable",
        "Cleanup and haul-away of light debris",
    ]


def _default_exclusions() -> List[str]:
    return [
        "Major drywall/wood repairs",
        "Mold remediation",
        "Moving heavy furniture",
    ]


# -------------------------
# Step: vision
# -------------------------
def step_vision_v1(state: PipelineState, step: StepConfig, assets: dict) -> StepResult:
    db: Session = assets["db"]
    lead: Lead = assets["lead"]

    vision_raw = run_vision_for_lead(db, lead.id)
    vision_raw = _ensure_obj(vision_raw)

    return StepResult(status="OK", data={"vision_raw": vision_raw})


# -------------------------
# Step: aggregate
# -------------------------
def step_aggregate_v1(
    state: PipelineState, step: StepConfig, assets: dict
) -> StepResult:
    vision_raw = (state.data.get("steps") or {}).get("vision", {}).get("vision_raw")
    vision_raw = _ensure_obj(vision_raw)

    vision = aggregate_vision(vision_raw)
    vision = _ensure_obj(vision)

    return StepResult(status="OK", data={"vision": vision})


# -------------------------
# Step: pricing (rules injected)
# -------------------------
def step_pricing_v1(state: PipelineState, step: StepConfig, assets: dict) -> StepResult:
    lead: Lead = assets["lead"]

    rules = assets.get("rules") if isinstance(assets, dict) else None

    vision = (state.data.get("steps") or {}).get("aggregate", {}).get("vision")
    vision = _ensure_obj(vision)

    pricing = run_pricing_engine(lead, vision, rules=rules)
    pricing = _ensure_obj(pricing)

    return StepResult(status="OK", data={"pricing": pricing})


# -------------------------
# Step: output (canonical PricingOutput dict)
# -------------------------
def step_output_v1(state: PipelineState, step: StepConfig, assets: dict) -> StepResult:
    lead: Lead = assets["lead"]

    vision = (state.data.get("steps") or {}).get("aggregate", {}).get("vision")
    pricing = (state.data.get("steps") or {}).get("pricing", {}).get("pricing")
    vision = _ensure_obj(vision)
    pricing = _ensure_obj(pricing)

    estimate = build_pricing_output(lead, vision, pricing)
    estimate = _ensure_obj(estimate)

    # Optional: ensure label exists (template expects item.label)
    try:
        for li in estimate.get("line_items") or []:
            if isinstance(li, dict) and not li.get("label"):
                # fallback: code or surface_type
                st = li.get("code") or li.get("surface_type") or "Item"
                li["label"] = str(st).replace("_", " ").title()
    except Exception:
        pass

    return StepResult(status="OK", data={"estimate_json": estimate})


# -------------------------
# Step: render (1.5.5 template per branch)
# -------------------------
def step_render_v1(state: PipelineState, step: StepConfig, assets: dict) -> StepResult:
    env = assets["jinja_env"]
    template_path = assets["template_path"]
    template = env.get_template(template_path)

    lead: Lead = assets.get("lead")

    # canonical pricing output (PricingOutput schema dump)
    pricing = (state.data.get("steps") or {}).get("output", {}).get(
        "estimate_json"
    ) or {}
    if not isinstance(pricing, dict):
        pricing = {}

    # raw pricing output (from pricing engine) to decide readiness
    pricing_raw = (state.data.get("steps") or {}).get("pricing", {}).get(
        "pricing"
    ) or {}
    if not isinstance(pricing_raw, dict):
        pricing_raw = {}

    pricing_ready = bool(
        (pricing_raw.get("total_usd") is not None)
        and (not bool(pricing_raw.get("needs_review", False)))
        and (pricing_raw.get("status") != "pricing_blocked")
    )

    meta = pricing.get("meta") if isinstance(pricing.get("meta"), dict) else {}
    project = {
        "lead_id": getattr(lead, "id", None) if lead else None,
        "estimate_id": meta.get("estimate_id")
        or (f"lead_{getattr(lead, 'id', '')}" if lead else ""),
        "date": str(meta.get("date") or dt.date.today().isoformat()),
        "valid_until": meta.get("valid_until"),
        "location": None,
    }

    reasons = (state.data.get("steps") or {}).get("needs_review", {}).get(
        "needs_review_reasons"
    ) or []
    needs_review = {
        "intro": "We detected uncertainty in the photos. Pricing is shown as TBD until a quick review.",
        "range_explanation": "A reviewer will confirm surfaces, prep level, and access. You’ll receive a finalized price shortly.",
        "reasons": reasons,
    }

    ctx = {
        "company": _default_company(),
        "copy": _default_copy(),
        "project": project,
        "pricing": pricing,
        "pricing_ready": pricing_ready,
        "needs_review": needs_review,
        "scope_bullets": _default_scope_bullets(),
        "exclusions": _default_exclusions(),
        "show_tax": False,
        "subject_to_verification_copy": "Final price may adjust after on-site verification.",
        "validity_copy": "This estimate is valid for 30 days.",
    }

    html = template.render(**ctx)
    return StepResult(status="OK", data={"estimate_html": html})


# -------------------------
# Step: store html (writes estimate_html_key)
# -------------------------
def step_store_html_v1(
    state: PipelineState, step: StepConfig, assets: dict
) -> StepResult:
    lead: Lead = assets.get("lead")
    if not lead:
        return StepResult(status="FAILED", error="missing_lead_in_assets")

    # config step id is "render_html"
    render_data = (state.data.get("steps") or {}).get("render_html") or {}
    html = render_data.get("estimate_html")
    if not html:
        return StepResult(
            status="FAILED", error="missing_estimate_html_from_render_step"
        )

    storage = get_storage()

    today = dt.date.today().isoformat()
    filename = f"estimate_{lead.id}_{uuid.uuid4().hex}.html"
    html_key = f"leads/{lead.id}/estimates/{today}/{filename}"

    storage.save_bytes(
        tenant_id=str(getattr(lead, "tenant_id", "")),
        key=html_key,
        data=html.encode("utf-8"),
    )

    return StepResult(status="OK", data={"estimate_html_key": html_key})


# -------------------------
# Step: needs review
# -------------------------
def step_needs_review_v1(
    state: PipelineState, step: StepConfig, assets: dict
) -> StepResult:
    estimate = (state.data.get("steps") or {}).get("output", {}).get(
        "estimate_json"
    ) or {}
    estimate = _ensure_obj(estimate)

    reasons = needs_review_from_output(estimate)
    needs_review = bool(reasons)

    # also enrich estimate meta for debugging / dashboard
    if isinstance(estimate, dict):
        meta = estimate.get("meta") if isinstance(estimate.get("meta"), dict) else {}
        meta["needs_review_reasons"] = reasons
        estimate["meta"] = meta

    return StepResult(
        status="NEEDS_REVIEW" if needs_review else "OK",
        data={"needs_review": needs_review, "needs_review_reasons": reasons},
        meta={"reasons": reasons},
    )

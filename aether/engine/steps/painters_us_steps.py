from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from aether.engine.context import PipelineState, StepResult
from aether.engine.config import StepConfig

from app.models import Lead
from app.models.upload_record import UploadRecord, UploadStatus
from app.services.storage import get_storage
from app.tasks.vision_task import run_vision_for_lead

from app.verticals.painters_us.vision_aggregate_us import (
    aggregate_images_to_surfaces as aggregate_vision,
)
from app.verticals.painters_us.pricing_engine_us import run_pricing_engine
from app.verticals.painters_us.pricing_output_builder import build_pricing_output
from app.verticals.painters_us.needs_review import needs_review_from_output

from app.services.photo_quality.inference import predict_photo_quality


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
# Step: photo quality (guardrail)
# -------------------------
def step_photo_quality_v1(
    state: PipelineState, step: StepConfig, assets: dict
) -> StepResult:
    """
    Photo quality guardrail.
    IMPORTANT: For MVP we do NOT hard-stop the pipeline here.
    We mark bad photos via step data + meta reasons, and let step_needs_review_v1
    combine reasons into the final outcome.

    This keeps the product deterministic and prevents false-SUCCESS while still
    allowing the render step to produce a "TBD / needs review" estimate.
    """
    lead: Lead = assets["lead"]
    db: Session = assets["db"]

    # Pull uploaded images for this lead (tenant-scoped)
    rows = (
        db.query(UploadRecord)
        .filter(UploadRecord.tenant_id == lead.tenant_id)
        .filter(UploadRecord.lead_id == lead.id)
        .filter(UploadRecord.status == UploadStatus.uploaded)
        .all()
    )

    image_refs: List[str] = [
        r.object_key
        for r in rows
        if isinstance(r.mime, str) and r.mime.startswith("image/")
    ]

    # Guardrail: no usable photos
    if not image_refs:
        reasons = ["no_photos"]
        return StepResult(
            status="OK",
            data={
                "photo_quality": {
                    "quality": "bad",
                    "score_bad": 1.0,
                    "reasons": reasons,
                    "bad": True,
                }
            },
            meta={"reasons": reasons},
        )

    storage = get_storage()
    tenant_id = str(getattr(lead, "tenant_id", ""))

    # Optional per-step threshold (future: set via painters_us.json step params)
    threshold_bad = 0.60
    try:
        params = getattr(step, "params", None) or {}
        if isinstance(params, dict) and params.get("threshold_bad") is not None:
            threshold_bad = float(params["threshold_bad"])
    except Exception:
        pass

    res = predict_photo_quality(
        image_refs=image_refs,
        storage=storage,
        tenant_id=tenant_id,
    )

    is_bad = (res.quality == "bad") or (float(res.score_bad or 0.0) >= threshold_bad)
    reasons = res.reasons or (["photo_quality_bad"] if is_bad else [])

    return StepResult(
        status="OK",
        data={
            "photo_quality": {
                "quality": res.quality,
                "score_bad": float(res.score_bad or 0.0),
                "reasons": reasons,
                "bad": bool(is_bad),
                "n_images": len(image_refs),
            }
        },
        meta={"reasons": reasons},
    )


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
    # base reasons from pricing output
    estimate = (state.data.get("steps") or {}).get("output", {}).get(
        "estimate_json"
    ) or {}
    estimate = _ensure_obj(estimate)

    reasons = needs_review_from_output(estimate) or []

    # merge in guardrail reasons from earlier steps (photo quality)
    pq = (
        (state.data.get("steps") or {})
        .get("photo_quality", {})
        .get("photo_quality", {})
    )
    prior_reasons = []
    if isinstance(pq, dict):
        prior_reasons = pq.get("reasons") or []
        if pq.get("bad") and not prior_reasons:
            prior_reasons = ["photo_quality_bad"]

    merged_reasons = list(dict.fromkeys((prior_reasons or []) + (reasons or [])))
    needs_review = bool(merged_reasons)

    # enrich estimate meta for debugging / dashboard
    if isinstance(estimate, dict):
        meta = estimate.get("meta") if isinstance(estimate.get("meta"), dict) else {}
        meta["needs_review_reasons"] = merged_reasons
        estimate["meta"] = meta

    return StepResult(
        status="NEEDS_REVIEW" if needs_review else "OK",
        data={"needs_review": needs_review, "needs_review_reasons": merged_reasons},
        meta={"reasons": merged_reasons},
    )

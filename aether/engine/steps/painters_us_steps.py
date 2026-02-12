from __future__ import annotations

import datetime as dt
import json
import logging
import re
import uuid
from decimal import Decimal
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from aether.engine.config import StepConfig
from aether.engine.context import PipelineState, StepResult

from app.models import Lead
from app.models.upload_record import UploadRecord, UploadStatus
from app.services.photo_quality.inference import predict_photo_quality
from app.services.storage import get_storage
from app.tasks.vision_task import run_vision_for_lead
from app.verticals.painters_us.needs_review import needs_review_from_output
from app.verticals.painters_us.pricing_engine_us import run_pricing_engine
from app.verticals.painters_us.pricing_output_builder import build_pricing_output
from app.verticals.painters_us.vision_aggregate_us import (
    aggregate_images_to_surfaces as aggregate_vision,
)

logger = logging.getLogger(__name__)


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


def _looks_like_image(object_key: str) -> bool:
    key = (object_key or "").lower()
    return key.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic"))


def _is_nonzero_money(x: Any) -> bool:
    if x is None:
        return False
    if isinstance(x, Decimal):
        return x > Decimal("0.00")
    if isinstance(x, (int, float)):
        return float(x) > 0
    if isinstance(x, str):
        s = x.strip().replace("$", "").replace(",", "")
        try:
            return float(s) > 0
        except Exception:
            return False
    return False


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
    """
    lead: Lead = assets["lead"]
    db: Session = assets["db"]

    rows = (
        db.query(UploadRecord)
        .filter(UploadRecord.tenant_id == lead.tenant_id)
        .filter(UploadRecord.lead_id == lead.id)
        .filter(UploadRecord.status.in_([UploadStatus.uploaded, "uploaded"]))
        .all()
    )

    logger.info(
        "PHOTO_QUALITY rows=%s lead_id=%s tenant_id=%s",
        len(rows),
        getattr(lead, "id", None),
        getattr(lead, "tenant_id", None),
    )
    if rows:
        r0 = rows[0]
        logger.info(
            "PHOTO_QUALITY sample mime=%s status=%s key=%s",
            getattr(r0, "mime", None),
            getattr(r0, "status", None),
            getattr(r0, "object_key", None),
        )

    image_refs: List[str] = []
    for r in rows:
        ok_mime = isinstance(r.mime, str) and r.mime.startswith("image/")
        ok_ext = _looks_like_image(getattr(r, "object_key", "") or "")
        if ok_mime or ok_ext:
            if isinstance(r.object_key, str) and r.object_key:
                image_refs.append(r.object_key)

    logger.info("PHOTO_QUALITY image_refs=%s", len(image_refs))

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
                    "n_images": 0,
                }
            },
            meta={"reasons": reasons},
        )

    storage = get_storage()
    tenant_id = str(getattr(lead, "tenant_id", ""))

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

    try:
        for li in estimate.get("line_items") or []:
            if isinstance(li, dict) and not li.get("label"):
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

    def _safe_json_dict(s: Any) -> Dict[str, Any]:
        if not isinstance(s, str) or not s.strip():
            return {}
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    def _clean_text(s: Any, max_len: int = 240) -> str:
        """
        Clean intake text so it never shows injected debug blobs / appended JSON.
        """
        if not isinstance(s, str):
            s = "" if s is None else str(s)

        s = s.strip()
        if not s:
            return ""

        # Normalize whitespace
        s = re.sub(r"\s+", " ", s).strip()
        lower = s.lower()

        # Cut on common injected/debug blobs (case-insensitive)
        cut_markers = [
            "vision_json",
            "vision json",
            "vision=",
            "debug",
            "trace_id=",
            "engine_status=",
            "image_predictions",
            "image_path",
            "model:",
            "reason:",
        ]
        for m in cut_markers:
            idx = lower.find(m)
            if idx != -1:
                s = s[:idx].strip()
                lower = s.lower()

        # If JSON still got appended without marker, cut at first "{"
        if "{" in s and not s.lstrip().startswith("{"):
            s = s.split("{", 1)[0].strip()

        s = s.rstrip(" -:;|,").strip()
        s = re.sub(r"\s+", " ", s).strip()

        if len(s) > max_len:
            s = s[: max_len - 1].rstrip() + "…"

        return s

    # --- pricing output (canonical) ---
    pricing = (state.data.get("steps") or {}).get("output", {}).get(
        "estimate_json"
    ) or {}
    pricing = _ensure_obj(pricing)
    if not isinstance(pricing, dict):
        pricing = {}

    # --- raw pricing (engine internal) ---
    pricing_raw = (state.data.get("steps") or {}).get("pricing", {}).get(
        "pricing"
    ) or {}
    pricing_raw = _ensure_obj(pricing_raw)
    if not isinstance(pricing_raw, dict):
        pricing_raw = {}

    # ✅ needs_review step runs AFTER render_html. Read reasons from estimate meta.
    meta = pricing.get("meta") if isinstance(pricing.get("meta"), dict) else {}
    reasons = meta.get("needs_review_reasons") or []
    if not isinstance(reasons, list):
        reasons = []

    is_provisional = "provisional_total" in reasons

    grand_total = None
    try:
        grand_total = (pricing.get("totals") or {}).get("grand_total")
    except Exception:
        grand_total = None

    # ✅ FINAL pricing only if non-zero AND not provisional
    pricing_ready = _is_nonzero_money(grand_total) and (not is_provisional)

    # -------------------------
    # ✅ Intake payload → context (US market)
    # -------------------------
    lead_payload = (
        _safe_json_dict(getattr(lead, "intake_payload", None)) if lead else {}
    )

    customer_name = (
        getattr(lead, "name", None) or lead_payload.get("name") or ""
    ).strip()
    customer_email = (
        getattr(lead, "email", None) or lead_payload.get("email") or ""
    ).strip()
    customer_phone = (
        getattr(lead, "phone", None) or lead_payload.get("phone") or ""
    ).strip()

    project_desc_raw = lead_payload.get("project_description") or ""
    address_raw = lead_payload.get("address") or ""

    project_desc = _clean_text(project_desc_raw)
    address = _clean_text(address_raw)

    # Remove duplicate "Address:" prefix if present
    if address and project_desc.lower().startswith("address:"):
        tmp = project_desc[len("address:") :].strip()
        if address.lower() in tmp.lower():
            tmp = re.sub(re.escape(address), "", tmp, flags=re.IGNORECASE).strip()
        project_desc = tmp.strip(" -:;|,").strip()

    # Location: prefer address, else short description
    location = (
        address or (project_desc[:80] + ("…" if len(project_desc) > 80 else "")) or None
    )

    # Area input: accept square_meters, convert to square feet
    square_meters = lead_payload.get("square_meters")
    try:
        sqm = float(square_meters) if square_meters is not None else None
    except Exception:
        sqm = None

    sqft = None
    if sqm is not None:
        try:
            sqft = int(round(sqm * 10.7639))  # 1 m² = 10.7639 ft²
        except Exception:
            sqft = None

    customer = {
        "name": customer_name or None,
        "email": customer_email or None,
        "phone": customer_phone or None,
    }

    project = {
        "lead_id": getattr(lead, "id", None) if lead else None,
        "estimate_id": meta.get("estimate_id")
        or (f"lead_{getattr(lead, 'id', '')}" if lead else ""),
        "date": str(meta.get("date") or dt.date.today().isoformat()),
        "valid_until": meta.get("valid_until"),
        "location": location,
        "square_feet": sqft,  # ✅ US native
        "description": project_desc or None,
    }

    needs_review_ctx = {
        "intro": "We detected uncertainty in the photos. Pricing is shown as TBD until a quick review.",
        "range_explanation": "A reviewer will confirm surfaces, prep level, and access. You’ll receive a finalized price shortly.",
        "reasons": reasons,
    }

    ctx = {
        "company": _default_company(),
        "copy": _default_copy(),
        "project": project,
        "customer": customer,
        "lead": lead,
        "pricing": pricing,
        "pricing_ready": pricing_ready,
        "pricing_is_estimate": bool(is_provisional),
        "needs_review": needs_review_ctx,
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

    reasons = needs_review_from_output(estimate) or []

    pq = (
        (state.data.get("steps") or {})
        .get("photo_quality", {})
        .get("photo_quality", {})
    )

    prior_reasons = []
    pq_bad = False
    if isinstance(pq, dict):
        prior_reasons = pq.get("reasons") or []
        pq_bad = bool(pq.get("bad"))
        if pq_bad and not prior_reasons:
            prior_reasons = ["photo_quality_bad"]

    merged_reasons = list(dict.fromkeys((prior_reasons or []) + (reasons or [])))

    PRICING_BLOCKERS = {
        "no_pricing_match",
        "missing_required_field",
        "too_few_images",
    }

    pricing_blocked = any(r in PRICING_BLOCKERS for r in (reasons or []))
    needs_review = bool(pq_bad or pricing_blocked)

    if isinstance(estimate, dict):
        meta = estimate.get("meta") if isinstance(estimate.get("meta"), dict) else {}
        meta["needs_review_reasons"] = merged_reasons
        meta["needs_review_hard"] = {
            "pq_bad": pq_bad,
            "pricing_blocked": pricing_blocked,
        }
        estimate["meta"] = meta

    return StepResult(
        status="NEEDS_REVIEW" if needs_review else "OK",
        data={
            "needs_review": needs_review,
            "needs_review_reasons": merged_reasons,
            "needs_review_hard": {
                "pq_bad": pq_bad,
                "pricing_blocked": pricing_blocked,
            },
        },
        meta={"reasons": merged_reasons},
    )

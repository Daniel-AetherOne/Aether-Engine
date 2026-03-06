from __future__ import annotations

import json
import uuid
import datetime as dt
from typing import Any
from sqlalchemy.orm import Session

from app.models import Lead
from app.tasks.vision_task import run_vision_for_lead

from app.verticals.paintly.vision_aggregate_us import (
    aggregate_images_to_quote_inputs as aggregate_vision,
)

from app.verticals.paintly.pricing_engine_us import run_pricing_engine
from app.verticals.paintly.pricing_output_builder import build_pricing_output
from app.verticals.paintly.needs_review import needs_review_from_output

from app.services.storage import get_storage


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


def _demo_vision() -> dict:
    """
    Fallback quote_inputs for leads without uploaded files.
    Keeps pricing predictable.
    """
    return {
        "area": {
            "value_m2": 75,
            "source": "demo",
            "confidence": 0.75,
            "sanity": {"status": "OK", "reason": None},
        },
        "scope": {
            "interior": True,
            "paint_walls": True,
            "paint_ceiling": False,
            "paint_trim": False,
        },
        "modifiers": {
            # NOTE: rules expect light/medium/heavy; "standard" will map to multiplier 1.0
            "prep_level": "light",
            "complexity": 1.1,
            "risk": {"cracks": False, "moisture": False},
        },
        "vision_signal_confidence": 0.8,
        "pricing_ready": True,
        "needs_review": False,
        "review_reasons": ["demo_mode"],
    }


def _extract_estimated_area(lead: Lead) -> float | None:
    """
    Extract estimated m² from intake.
    Supports:
      - lead.estimated_area_m2
      - lead.square_meters
      - lead.intake_payload (JSON string) with square_meters/area_sqm
      - dict-ish fields lead.data/lead.payload/lead.intake
    """
    # 1) direct columns
    for attr in ("estimated_area_m2", "square_meters"):
        if hasattr(lead, attr):
            v = getattr(lead, attr, None)
            if v:
                try:
                    f = float(v)
                    if f > 0:
                        return f
                except Exception:
                    pass

    # 2) intake_payload JSON string
    raw = getattr(lead, "intake_payload", None)
    if raw:
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                v = (
                    payload.get("square_meters")
                    or payload.get("area_sqm")
                    or payload.get("estimated_area_m2")
                )
                if v is not None:
                    f = float(v)
                    if f > 0:
                        return f
        except Exception:
            pass

    # 3) dict fields
    for attr in ("data", "payload", "intake"):
        val = getattr(lead, attr, None)
        if isinstance(val, dict):
            v = (
                val.get("square_meters")
                or val.get("area_sqm")
                or val.get("estimated_area_m2")
                or val.get("area_m2")
            )
            if v is not None:
                try:
                    f = float(v)
                    if f > 0:
                        return f
                except Exception:
                    pass

    return None


def compute_quote_for_lead(db: Session, lead: Lead, render_html: bool = True) -> dict:
    # --------------------------------------------------
    # 1) Vision stage
    # --------------------------------------------------
    try:
        vision_raw = run_vision_for_lead(db, lead.id)
        vision_raw = _ensure_obj(vision_raw)

        estimated_area_m2 = _extract_estimated_area(lead)

        scope = {
            "interior": True,
            "paint_walls": True,
            "paint_ceiling": False,
            "paint_trim": False,
        }

        # Unwrap: run_vision_for_lead returns a dict with "image_predictions"
        image_predictions = (
            vision_raw.get("image_predictions")
            if isinstance(vision_raw, dict)
            else vision_raw
        )
        image_predictions = _ensure_obj(image_predictions)

        vision = aggregate_vision(
            image_predictions=image_predictions,
            estimated_area_m2=estimated_area_m2,
            scope=scope,
        )
        vision = _ensure_obj(vision)

    except ValueError as e:
        if "No files found for this lead" in str(e):
            vision = _demo_vision()
        else:
            raise

    # --------------------------------------------------
    # 2) Pricing stage
    # --------------------------------------------------
    pricing = run_pricing_engine(lead, vision)
    pricing = _ensure_obj(pricing)

    # --------------------------------------------------
    # 3) Output builder
    # --------------------------------------------------
    estimate = build_pricing_output(lead, vision, pricing)
    estimate = _ensure_obj(estimate)

    # Attach vision info to meta (once)
    if isinstance(estimate, dict):
        meta = estimate.get("meta") if isinstance(estimate.get("meta"), dict) else {}
        if isinstance(vision, dict):
            meta["vision_needs_review"] = bool(vision.get("needs_review", False))
            meta["vision_review_reasons"] = vision.get("review_reasons", [])
            meta["vision_signal_confidence"] = vision.get(
                "vision_signal_confidence", None
            )

            area = (
                (vision.get("area") or {})
                if isinstance(vision.get("area"), dict)
                else {}
            )
            meta["area_m2"] = area.get("value_m2", None)

        estimate["meta"] = meta

    # --------------------------------------------------
    # 4) Needs review logic
    # --------------------------------------------------
    reasons = needs_review_from_output(estimate)
    needs_review = bool(reasons)

    if isinstance(estimate, dict):
        meta = estimate.get("meta") if isinstance(estimate.get("meta"), dict) else {}
        meta["needs_review_reasons"] = reasons
        estimate["meta"] = meta

    # --------------------------------------------------
    # 5) Optional HTML render + store
    # --------------------------------------------------
    html_key = None

    if render_html:
        # Import lazily to avoid boot failure when render dependencies/constants mismatch
        from app.verticals.paintly.render_estimate import render_estimate_html

        html = render_estimate_html(estimate)

        storage = get_storage()
        today = dt.date.today().isoformat()
        filename = f"estimate_{lead.id}_{uuid.uuid4().hex}.html"
        html_key = f"leads/{lead.id}/estimates/{today}/{filename}"

        storage.save_bytes(
            tenant_id=str(lead.tenant_id),
            key=html_key,
            data=html.encode("utf-8"),
            content_type="text/html; charset=utf-8",
        )

    return {
        "estimate_json": estimate,
        "estimate_html_key": html_key,
        "needs_review": needs_review,
    }

from __future__ import annotations

import json
import uuid
import datetime as dt
from typing import Any
from sqlalchemy.orm import Session

from app.models import Lead
from app.tasks.vision_task import run_vision_for_lead

from app.verticals.painters_us.vision_aggregate_us import (
    aggregate_images_to_surfaces as aggregate_vision,
)
from app.verticals.painters_us.pricing_engine_us import run_pricing_engine
from app.verticals.painters_us.pricing_output_builder import build_pricing_output
from app.verticals.painters_us.render_estimate import render_estimate_html
from app.verticals.painters_us.needs_review import needs_review_from_output

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
    Fallback vision output for leads without uploaded files.
    Keep it small & predictable so pricing/render always work.
    """
    return {
        "surfaces": [
            {"label": "Living room walls", "surface_type": "walls", "sqft": 550},
            {"label": "Bedroom walls", "surface_type": "walls", "sqft": 420},
            {"label": "Trim & baseboards", "surface_type": "trim", "linear_ft": 180},
        ]
    }


def compute_quote_for_lead(db: Session, lead: Lead) -> dict:
    # 1) Vision (with demo fallback)
    try:
        vision_raw = run_vision_for_lead(db, lead.id)
        vision_raw = _ensure_obj(vision_raw)

        vision = aggregate_vision(vision_raw)
        vision = _ensure_obj(vision)

    except ValueError as e:
        # If no files exist for this lead, fall back to demo vision
        if "No files found for this lead" in str(e):
            vision = _demo_vision()
        else:
            raise

    # 2) Pricing
    pricing = run_pricing_engine(lead, vision)
    pricing = _ensure_obj(pricing)

    # 3) Output builder (dict / JSON-serializable)
    estimate = build_pricing_output(lead, vision, pricing)
    estimate = _ensure_obj(estimate)

    # 4) HTML render
    html = render_estimate_html(estimate)

    # 5) Store HTML (local or S3)
    storage = get_storage()
    today = dt.date.today().isoformat()
    filename = f"estimate_{lead.id}_{uuid.uuid4().hex}.html"

    # key WITHOUT tenant prefix; storage backend prefixes internally
    html_key = f"leads/{lead.id}/estimates/{today}/{filename}"

    storage.save_bytes(
        tenant_id=str(lead.tenant_id),
        key=html_key,
        data=html.encode("utf-8"),
        content_type="text/html; charset=utf-8",
    )

    # 6) Needs review?
    reasons = needs_review_from_output(estimate)
    needs_review = bool(reasons)

    # keep reasons in meta
    if isinstance(estimate, dict):
        meta = estimate.get("meta") if isinstance(estimate.get("meta"), dict) else {}
        meta["needs_review_reasons"] = reasons
        meta["demo_mode"] = True
        estimate["meta"] = meta

    return {
        "estimate_json": estimate,
        "estimate_html_key": html_key,
        "needs_review": needs_review,
    }

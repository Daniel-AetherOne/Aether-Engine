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


def compute_quote_for_lead(db: Session, lead: Lead) -> dict:
    # 1) Vision
    vision_raw = run_vision_for_lead(db, lead.id)
    vision_raw = _ensure_obj(vision_raw)

    vision = aggregate_vision(vision_raw)
    vision = _ensure_obj(vision)

    # 2) Pricing
    pricing = run_pricing_engine(lead, vision)
    pricing = _ensure_obj(pricing)

    print("DEBUG pricing passed to builder:", pricing)

    print("DEBUG type:", type(pricing))

    if isinstance(pricing, dict):
        print("DEBUG pricing keys:", pricing.keys())
    elif hasattr(pricing, "data"):
        print("DEBUG pricing.data keys:", pricing.data.keys())

    # 3) Output builder (should return a dict / JSON-serializable object)
    estimate = build_pricing_output(lead, vision, pricing)
    estimate = _ensure_obj(estimate)

    # 4) HTML render (expects dict-like estimate)
    html = render_estimate_html(estimate)

    # 5) Store HTML (local or S3 via storage backend)
    storage = get_storage()

    today = dt.date.today().isoformat()
    filename = f"estimate_{lead.id}_{uuid.uuid4().hex}.html"
    # key WITHOUT tenant prefix; storage backend can prefix internally if needed
    html_key = f"leads/{lead.id}/estimates/{today}/{filename}"

    storage.save_bytes(
        tenant_id=lead.tenant_id,
        key=html_key,
        data=html.encode("utf-8"),
    )

    # 6) Needs review?
    reasons = needs_review_from_output(estimate)
    needs_review = bool(reasons)

    # handig voor debug / later internal dashboard
    if isinstance(estimate, dict):
        meta = estimate.get("meta") if isinstance(estimate.get("meta"), dict) else {}
        meta["needs_review_reasons"] = reasons
        estimate["meta"] = meta

    return {
        "estimate_json": estimate,  # keep as dict/object; adapter serializes for DB
        "estimate_html_key": html_key,
        "needs_review": needs_review,
    }

from __future__ import annotations

import json
from pathlib import Path
from sqlalchemy.orm import Session

from app.models import Lead

from aether.engine.context import EngineContext
from aether.engine.config import load_engine_config
from aether.engine.registry import StepRegistry
from aether.engine.runner import run_pipeline
from aether.engine.steps import register_all


def compute_quote_for_lead_engine(db: Session, lead: Lead) -> dict:
    # 1) load config
    raw = json.loads(
        Path("app/engine_config/painters_us.json").read_text(encoding="utf-8")
    )
    cfg = load_engine_config(raw)

    # 2) registry
    registry = StepRegistry()
    register_all(registry)

    # 3) context
    ctx = EngineContext(
        tenant_id=str(lead.tenant_id),
        vertical_id="painters_us",
        lead_id=str(lead.id),
    )

    # 4) assets: keep it minimal for now
    assets = {
        "db": db,
        "lead": lead,
        # later: "rules": ..., "template": ...
    }

    # 5) run
    state = run_pipeline(
        context=ctx,
        config=cfg,
        registry=registry,
        assets=assets,
        initial_data={},  # optional; steps use assets/db/lead
    )

    estimate = state.data["steps"]["output"]["estimate_json"]
    html_key = state.data["steps"]["store_html"]["estimate_html_key"]
    needs_review = state.data["steps"]["needs_review"]["needs_review"]

    return {
        "estimate_json": estimate,
        "estimate_html_key": html_key,
        "needs_review": needs_review,
        # optional debug: "engine_status": state.status, "logs": state.logs
    }

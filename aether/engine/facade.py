from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.models import Lead

from aether.engine.assets import load_assets, repo_root
from aether.engine.context import EngineContext
from aether.engine.config import load_engine_config
from aether.engine.registry import StepRegistry
from aether.engine.runner import run_pipeline
from aether.engine.steps import register_all


def _load_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _tail(xs: list, n: int = 50) -> list:
    return xs[-n:] if xs else []


def compute_quote_for_lead_v15(
    db: Session, lead: Lead, vertical_id: str
) -> Dict[str, Any]:
    root = repo_root()

    # 1) load engine config
    cfg_path = root / "engine_config" / f"{vertical_id}.json"
    cfg = load_engine_config(_load_json(cfg_path))

    # 2) registry
    registry = StepRegistry()
    register_all(registry)

    # 3) context
    ctx = EngineContext(
        tenant_id=str(lead.tenant_id),
        vertical_id=vertical_id,
        lead_id=str(lead.id),
    )

    # 4) rules
    rules_dict: Dict[str, Any] = {}
    if cfg.rules_path:
        rp = root / cfg.rules_path
        if rp.exists():
            rules_dict = _load_json(rp)

    # 5) assets (template + jinja env)
    assets_obj = load_assets(cfg, rules=rules_dict)

    assets = {
        "db": db,
        "lead": lead,
        "rules": rules_dict,
        "jinja_env": assets_obj.jinja_env,
        "template_path": assets_obj.template_path,
    }

    # 6) run pipeline
    state = run_pipeline(
        context=ctx,
        config=cfg,
        registry=registry,
        assets=assets,
        initial_data={},
    )

    logs = getattr(state, "logs", []) or []
    failure_step = getattr(state, "failure_step", None)

    # ✅ Only raise on FAILED. NEEDS_REVIEW is a valid outcome.
    if state.status == "FAILED":
        error_summary = None
        for entry in reversed(logs):
            if (
                isinstance(entry, dict)
                and entry.get("message") == "step_end"
                and entry.get("step_id") == failure_step
                and entry.get("error")
            ):
                error_summary = entry.get("error")
                break

        available_steps = list((state.data.get("steps") or {}).keys())

        raise RuntimeError(
            "engine_pipeline_failed:"
            f"(status={state.status}, "
            f"failure_step={failure_step}, "
            f"error={error_summary}, "
            f"available_steps={available_steps}, "
            f"logs_tail={_tail(logs, 25)})"
        )

    # ✅ Success OR needs-review: return best-effort outputs
    steps = state.data.get("steps") or {}

    output_step = steps.get("output") or {}
    store_step = steps.get("store_html") or {}
    nr_step = steps.get("needs_review") or {}

    estimate = output_step.get("estimate_json")
    html_key = store_step.get("estimate_html_key")

    # needs_review bool: prefer step output, else infer from state.status
    needs_review = bool(nr_step.get("needs_review", state.status == "NEEDS_REVIEW"))

    # If HTML wasn't stored, that's an actual engine wiring bug
    if not html_key:
        available_steps = list(steps.keys())
        raise RuntimeError(
            "engine_missing_estimate_html_key:"
            f"(status={state.status}, available_steps={available_steps}, logs_tail={_tail(logs, 25)})"
        )

    return {
        "estimate_json": estimate,
        "estimate_html_key": html_key,
        "needs_review": needs_review,
        "engine_status": state.status,
        "trace_id": ctx.trace_id,
    }

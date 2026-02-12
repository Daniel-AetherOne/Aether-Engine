from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

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


def _step_payload(step: Any) -> Dict[str, Any]:
    """
    Steps in state.data["steps"] are usually StepResult objects:
      StepResult(status=..., data={...}, ...)
    but sometimes they may already be plain dicts.
    This helper always returns the underlying payload dict.
    """
    if step is None:
        return {}
    if isinstance(step, dict):
        # Sometimes serialized StepResult: {"status": "...", "data": {...}}
        if isinstance(step.get("data"), dict):
            return step.get("data") or {}
        return step
    data = getattr(step, "data", None)
    if isinstance(data, dict):
        return data
    # Pydantic models etc.
    if hasattr(step, "model_dump"):
        try:
            d = step.model_dump()
            if isinstance(d, dict) and isinstance(d.get("data"), dict):
                return d["data"]
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}
    if hasattr(step, "dict"):
        try:
            d = step.dict()
            if isinstance(d, dict) and isinstance(d.get("data"), dict):
                return d["data"]
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}
    return {}


def _extract_pricing_raw(steps: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Your pricing step payload is currently shaped like:
      {"pricing": {...actual pricing dict...}}
    This function returns the inner dict.
    """
    pricing_step = steps.get("pricing") if isinstance(steps, dict) else None
    payload = _step_payload(pricing_step)
    if not payload:
        return None

    inner = payload.get("pricing")
    if isinstance(inner, dict):
        return inner

    return payload if isinstance(payload, dict) else None


def _as_decimal_str(x: Any) -> Optional[str]:
    if x is None:
        return None
    try:
        d = Decimal(str(x))
        # normalize to 2dp string
        return f"{d:.2f}"
    except Exception:
        return None


def _apply_option1_provisional_total_if_missing(
    estimate: Any,
    pricing_raw: Optional[Dict[str, Any]],
    *,
    minimum_total_usd: str = "500.00",  # ✅ MVP safety net; adjust to taste
) -> tuple[Any, bool]:
    """
    Option 1:
    If estimate totals are missing/zero BUT pricing_raw has estimate_range,
    set totals to high_usd (else low_usd) and add a provisional line_item.

    If estimate_range exists but is 0.0 (your current case), use minimum_total_usd
    so customer never sees $0.00.
    """
    if not isinstance(estimate, dict):
        return estimate, False
    if not isinstance(pricing_raw, dict):
        return estimate, False

    er = pricing_raw.get("estimate_range")
    if not isinstance(er, dict):
        return estimate, False

    chosen = er.get("high_usd") or er.get("low_usd")
    chosen_str = _as_decimal_str(chosen)

    # If estimate_range resolves to 0.00 (your current case), apply MVP minimum.
    if not chosen_str or chosen_str == "0.00":
        chosen_str = minimum_total_usd

    totals = estimate.get("totals") or {}
    if not isinstance(totals, dict):
        totals = {}

    gt = totals.get("grand_total")
    gt_str = _as_decimal_str(gt)

    # missing if None or "0.00"
    missing = (gt is None) or (gt_str is None) or (gt_str == "0.00")
    if not missing:
        return estimate, False

    # set totals
    totals["pre_tax"] = chosen_str
    totals["grand_total"] = chosen_str
    estimate["totals"] = totals

    # ensure at least one line item
    lis = estimate.get("line_items")
    if not isinstance(lis, list) or len(lis) == 0:
        estimate["line_items"] = [
            {
                "code": "provisional_estimate",
                "label": "Interior painting (estimate)",
                "description": "Provisional estimate (Option 1). Final price after quick review.",
                "quantity": 1,
                "unit": "job",
                "unit_price": chosen_str,
                "total": chosen_str,
                "category": "labor",
                "assumptions": {},
            }
        ]

    # update meta reasons
    meta = estimate.get("meta") or {}
    if not isinstance(meta, dict):
        meta = {}
    reasons = meta.get("needs_review_reasons") or []
    if not isinstance(reasons, list):
        reasons = []

    # remove missing_total, add provisional_total
    reasons = [r for r in reasons if r != "missing_total"]
    if "provisional_total" not in reasons:
        reasons.append("provisional_total")

    meta["needs_review_reasons"] = reasons
    estimate["meta"] = meta

    return estimate, True


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

    steps = (state.data.get("steps") or {}) if isinstance(state.data, dict) else {}
    available_steps = list(steps.keys()) if isinstance(steps, dict) else []

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

        raise RuntimeError(
            "engine_pipeline_failed:"
            f"(status={state.status}, "
            f"failure_step={failure_step}, "
            f"error={error_summary}, "
            f"available_steps={available_steps}, "
            f"logs_tail={_tail(logs, 25)})"
        )

    # ✅ Success OR needs-review: return best-effort outputs
    output_step = _step_payload(steps.get("output"))
    store_step = _step_payload(steps.get("store_html"))
    nr_step = _step_payload(steps.get("needs_review"))

    estimate = output_step.get("estimate_json")
    html_key = store_step.get("estimate_html_key")

    # needs_review bool: prefer step output, else infer from state.status
    needs_review = bool(nr_step.get("needs_review", state.status == "NEEDS_REVIEW"))

    # ---- Debug-friendly extras + raw pricing payload ----
    pricing_raw = _extract_pricing_raw(steps)

    # ---- Option 1: force provisional totals if missing_total but we have estimate_range ----
    estimate, forced_needs_review = _apply_option1_provisional_total_if_missing(
        estimate,
        pricing_raw,
        minimum_total_usd="500.00",  # <-- change if you want
    )
    if forced_needs_review:
        needs_review = True

    # ---- Also: if estimate itself says reasons exist, mark needs_review=True ----
    try:
        if isinstance(estimate, dict):
            meta = estimate.get("meta") or {}
            reasons = meta.get("needs_review_reasons") or []
            if isinstance(reasons, list) and reasons:
                needs_review = True
    except Exception:
        pass

    # If HTML wasn't stored, that's an actual engine wiring bug
    if not html_key:
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
        # ✅ expose for adapter debug
        "available_steps": available_steps,
        "logs_tail": _tail(logs, 25),
        "debug_pricing_raw": pricing_raw,
    }

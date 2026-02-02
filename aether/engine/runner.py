# aether/engine/runner.py
from __future__ import annotations
from typing import Any, Dict, Optional
from .context import EngineContext, PipelineState, StepResult
from .config import EngineConfig
from .registry import StepRegistry


def _log(state: PipelineState, level: str, msg: str, **fields: Any) -> None:
    state.logs.append(
        {
            "level": level,
            "message": msg,
            "tenant_id": state.context.tenant_id,
            "vertical_id": state.context.vertical_id,
            "lead_id": state.context.lead_id,
            "trace_id": state.context.trace_id,
            **fields,
        }
    )


def run_pipeline(
    context: EngineContext,
    config: EngineConfig,
    registry: StepRegistry,
    assets: Dict[str, Any],
    initial_data: Optional[Dict[str, Any]] = None,
) -> PipelineState:
    state = PipelineState(context=context, data=initial_data or {})

    _log(state, "info", "pipeline_start", config_version=config.version)

    for step_cfg in config.steps:
        _log(state, "info", "step_start", step_id=step_cfg.id, step_use=step_cfg.use)

        try:
            step_fn = registry.get(step_cfg.use)
            result: StepResult = step_fn(state, step_cfg, assets)

        except Exception as e:
            # write error into pipeline logs so we can surface it later
            _log(
                state,
                "error",
                "step_exception",
                step_id=step_cfg.id,
                step_use=step_cfg.use,
                exc=f"{type(e).__name__}: {e}",
            )
            result = StepResult(status="FAILED", error=f"{type(e).__name__}: {e}")

        _log(
            state,
            "info" if result.status == "OK" else "warning",
            "step_end",
            step_id=step_cfg.id,
            status=result.status,
            error=result.error,
            meta=result.meta,
        )

        state.data.setdefault("steps", {})
        state.data["steps"][step_cfg.id] = result.data or {}

        if result.status == "FAILED":
            state.status = "FAILED"
            state.failure_step = step_cfg.id
            if step_cfg.on_fail == "CONTINUE":
                _log(state, "warning", "step_failed_continue", step_id=step_cfg.id)
                continue
            _log(state, "error", "pipeline_failed", failure_step=step_cfg.id)
            return state

        if result.status == "NEEDS_REVIEW":
            state.status = "NEEDS_REVIEW"
            state.failure_step = step_cfg.id
            if step_cfg.on_needs_review == "CONTINUE":
                _log(
                    state, "warning", "step_needs_review_continue", step_id=step_cfg.id
                )
                continue
            _log(state, "warning", "pipeline_needs_review", review_step=step_cfg.id)
            return state

    state.status = "SUCCEEDED"
    _log(state, "info", "pipeline_succeeded")
    return state

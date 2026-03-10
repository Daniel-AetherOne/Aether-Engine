# aether/engine/steps/vision.py
from __future__ import annotations
from aether.engine.context import PipelineState, StepResult
from aether.engine.config import StepConfig

def vision_v1(state: PipelineState, step: StepConfig, assets: dict) -> StepResult:
    # assets kan bevatten: vision_client, db, s3, etc.
    # state.data bevat bv: lead, image_keys
    image_keys = state.data.get("image_keys", [])
    if not image_keys:
        return StepResult(status="FAILED", error="No image_keys in state.data")

    # TODO: call your existing vision worker/service
    # vision_out = assets["vision_client"].run(...)
    vision_out = {"rooms": [], "confidence": 0.0}  # stub

    # Always return OK here; Paintly-specific needs_review
    # is decided centrally in paintly_steps.needs_review_v1.
    # We still surface confidence/diagnostic info via meta.
    meta = {}
    try:
        conf = float(vision_out.get("confidence", 1.0))
        meta["confidence"] = conf
        if conf < 0.4:
            meta["low_confidence"] = True
            meta.setdefault("reasons", []).append("vision_low_confidence")
    except Exception:
        pass

    return StepResult(status="OK", data=vision_out, meta=meta)

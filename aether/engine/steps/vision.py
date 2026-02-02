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

    # Optionally decide NEEDS_REVIEW early if low confidence
    if vision_out.get("confidence", 1.0) < 0.4:
        return StepResult(status="NEEDS_REVIEW", data=vision_out, meta={"reason": "low_confidence"})

    return StepResult(status="OK", data=vision_out)

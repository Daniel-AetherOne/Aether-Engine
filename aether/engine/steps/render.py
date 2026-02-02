from aether.engine.context import PipelineState, StepResult
from aether.engine.config import StepConfig


def render_jinja_v1(state: PipelineState, step: StepConfig, assets: dict) -> StepResult:
    return StepResult(status="OK", data={"html": "<h1>Pipeline works 🎉</h1>"})

from .painters_us_steps import (
    step_vision_v1,
    step_aggregate_v1,
    step_pricing_v1,
    step_output_v1,
    step_render_v1,
    step_store_html_v1,
    step_needs_review_v1,
)


def register_all(registry):
    registry.register("vision.v1", step_vision_v1)
    registry.register("aggregate.v1", step_aggregate_v1)
    registry.register("pricing.v1", step_pricing_v1)
    registry.register("output.v1", step_output_v1)
    registry.register("render.v1", step_render_v1)
    registry.register("store_html.v1", step_store_html_v1)
    registry.register("needs_review.v1", step_needs_review_v1)

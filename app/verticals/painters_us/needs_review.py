# app/verticals/painters_us/needs_review.py

from dataclasses import dataclass


@dataclass(frozen=True)
class NeedsReviewCopy:
    badge: str
    intro: str
    range_explanation: str
    cta_title: str
    cta_body: str


US_PAINTERS_NEEDS_REVIEW_COPY = NeedsReviewCopy(
    badge="Estimate Needs Review",

    intro=(
        "Some areas in this project could not be priced with high confidence based on the "
        "available photos and details. To avoid over- or under-estimating, this estimate "
        "is provided as a range."
    ),

    range_explanation=(
        "The range below reflects possible preparation requirements, access constraints, "
        "and surface conditions that will be confirmed before final pricing."
    ),

    cta_title="Next Step: Confirm Details",
    cta_body=(
        "To provide a precise estimate, please share additional photos or schedule a brief "
        "on-site inspection. Once reviewed, we’ll confirm scope and finalize pricing."
    ),
)

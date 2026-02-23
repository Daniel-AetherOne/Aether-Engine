# app/verticals/painters_us/disclaimer.py

from dataclasses import dataclass


@dataclass(frozen=True)
class EstimateDisclaimer:
    text: str
    validity_days: int


US_PAINTERS_ESTIMATE_DISCLAIMER = EstimateDisclaimer(
    validity_days=30,
    text=(
        "This document is an Estimate only and is provided for informational purposes. "
        "Pricing is based on the information, photos, and descriptions provided, as well as "
        "typical site conditions.\n\n"
        "Final pricing may change following an on-site inspection or verification if actual "
        "conditions differ from those assumed, including but not limited to surface condition, "
        "preparation requirements, access limitations, safety considerations, or hidden damage "
        "(such as rot, moisture, or previously concealed defects).\n\n"
        "This Estimate is valid for 30 days from the date of issue and is subject to scheduling "
        "availability. Exterior work schedules may be affected by weather conditions.\n\n"
        "Sales tax may apply where required by law. This Estimate does not constitute a contract, "
        "guarantee, or invoice, and no work will be scheduled until scope and pricing are confirmed."
    ),
)

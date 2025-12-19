# app/verticals/painters_us/assumptions.py

from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeAndAssumptions:
    # What IS included
    included: list[str]

    # What is explicitly NOT included
    not_included: list[str]

    # Conditions under which pricing/scope may change
    change_conditions: list[str]


US_PAINTERS_SCOPE_ASSUMPTIONS = ScopeAndAssumptions(
    included=[
        "Surface preparation as noted (light sanding, scraping, patching as required).",
        "Priming of repaired or bare areas as needed.",
        "Application of finish coats to listed surfaces only.",
        "Standard protection of adjacent surfaces (masking, drop cloths).",
        "Daily cleanup of work areas related to painting activities.",
    ],
    not_included=[
        "Structural repairs, carpentry, or drywall replacement.",
        "Extensive repair of hidden damage (rot, mold, moisture intrusion).",
        "Lead paint abatement or hazardous material removal.",
        "Wallpaper removal or specialty coatings unless explicitly listed.",
        "Moving or storing large furniture or personal belongings.",
        "Permit fees or inspections unless specifically stated.",
    ],
    change_conditions=[
        "Pricing may change if on-site conditions differ materially from those visible in provided photos or descriptions.",
        "Additional preparation may be required if surfaces are found to be in poorer condition than assumed.",
        "Scope or pricing adjustments may occur if access limitations, safety requirements, or working hours differ from initial assumptions.",
        "Customer-requested scope changes, color changes, or additional areas will be priced separately.",
        "Weather conditions may affect scheduling for exterior work.",
    ],
)

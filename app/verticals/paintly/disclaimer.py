from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class EstimateDisclaimer:
    """
    Simple container for disclaimer content. For Paintly EU we only
    currently use the bullet list in templates.
    """

    bullets: List[str]


PAINTLY_ESTIMATE_DISCLAIMER = EstimateDisclaimer(
    bullets=[
        "Werkzaamheden zijn gebaseerd op de huidige staat van de ondergrond en normale bereikbaarheid.",
        "Eventuele extra reparaties (scheuren, losse delen, vochtproblemen) worden apart beoordeeld en geprijsd.",
        "Planningen kunnen wijzigen bij extreme weersomstandigheden of onvoorziene situaties op locatie.",
    ]
)


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


# -------------------------------------------------------------------
# Paintly (EU) scope assumptions expected by render_estimate.py
# render_estimate.py reads: getattr(PAINTLY_SCOPE_ASSUMPTIONS, "included", None)
# -------------------------------------------------------------------

PAINTLY_SCOPE_ASSUMPTIONS = ScopeAndAssumptions(
    included=[
        "Voorbereiding van oppervlakken waar nodig (licht schuren, bijwerken, primer op reparaties).",
        "Aanbrengen van afwerklagen op alleen de genoemde oppervlakken.",
        "Standaard afplakken/beschermen van aangrenzende delen.",
        "Oplever-schoonmaak gerelateerd aan het schilderwerk.",
    ],
    not_included=[
        "Constructieve reparaties, timmerwerk, of vervanging van plaatmateriaal.",
        "Herstel van verborgen schade (rot, schimmel, vochtproblemen) tenzij expliciet opgenomen.",
        "Verwijderen van oude behanglagen of speciale coatings tenzij expliciet opgenomen.",
        "Verplaatsen/opslag van grote meubels of volledige woning-inboedel.",
        "Vergunningen of keuringen tenzij expliciet opgenomen.",
    ],
    change_conditions=[
        "Prijs kan wijzigen als de situatie ter plekke afwijkt van foto’s/omschrijving.",
        "Extra voorbereiding kan nodig zijn bij slechtere ondergrond dan verwacht.",
        "Wijzigingen in scope (extra ruimtes, extra lagen, kleurwijzigingen) worden apart geprijsd.",
        "Bij buitenwerk kan planning wijzigen door weersomstandigheden.",
    ],
)

# Backwards compatible export expected by render_estimate.py
PAINTLY_SCOPE_ASSUMPTIONS = {
    "includes_paint": False,
    "includes_prep": False,
    "includes_cleanup": False,
    "includes_repairs": False,
    "includes_materials": False,
    "includes_labor": False,
}

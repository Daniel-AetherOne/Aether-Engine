from __future__ import annotations

from typing import Optional

COUNTRY_DEFAULT_LANG = {
    "NL": "nl",
    "BE": "nl",  # later: nl/fr, nu ok
    "DE": "de",
    "SE": "en",  # of "sv" later
    "NO": "en",
    "DK": "en",
    "FI": "en",
}

SUPPORTED = {"nl", "en", "de"}  # later uitbreiden


def pick_language(
    *, country: Optional[str], accept_language: Optional[str], fallback: str = "nl"
) -> str:
    # 1) country default
    c = (country or "").upper().strip()
    if c in COUNTRY_DEFAULT_LANG:
        base = COUNTRY_DEFAULT_LANG[c]
    else:
        base = fallback

    # 2) browser hint (Accept-Language)
    al = (accept_language or "").lower()
    if not al:
        return base if base in SUPPORTED else fallback

    # simple parse: check preferred order
    # e.g. "nl-NL,nl;q=0.9,en;q=0.8"
    prefs = [p.split(";")[0].strip() for p in al.split(",") if p.strip()]
    for p in prefs:
        code = p.split("-")[0]
        if code in SUPPORTED:
            return code

    return base if base in SUPPORTED else fallback

from __future__ import annotations

VAT_BY_COUNTRY = {
    "NL": 0.09,
    "BE": 0.06,
    "DE": 0.19,
    "SE": 0.25,
    "NO": 0.25,
    "DK": 0.25,
    "FI": 0.25,
}

TZ_BY_COUNTRY = {
    "NL": "Europe/Amsterdam",
    "BE": "Europe/Brussels",
    "DE": "Europe/Berlin",
    "SE": "Europe/Stockholm",
    "NO": "Europe/Oslo",
    "DK": "Europe/Copenhagen",
    "FI": "Europe/Helsinki",
}


def resolve_eu_config(country: str | None) -> dict:
    c = (country or "NL").upper().strip()
    return {
        "country": c,
        "currency": "EUR",
        "units": "metric",
        "vat_rate": VAT_BY_COUNTRY.get(c, 0.0),
        "timezone": TZ_BY_COUNTRY.get(c, "Europe/Amsterdam"),
        "language": "nl",
    }

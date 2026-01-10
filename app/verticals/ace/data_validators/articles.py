from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import (
    ValidationResult,
    ValidationError,
    ValidationWarning,
    _err,
    _warn,
    parse_csv,
    require_headers,
    get_cell,
    to_str,
    to_decimal,
)

CURRENCY_WHITELIST = {"EUR", "USD", "GBP"}

# Headers (allow NL/EN variants)
H_SKU = ["SKU", "Sku", "Artikel", "Artikelnummer", "ItemCode"]
H_DESC = ["Omschrijving", "Description", "Product", "Naam", "Name"]
H_COST = ["Inkoopprijs", "Cost", "PurchasePrice", "Inkoop"]
H_CUR = ["Valuta", "Currency"]
H_WEIGHT = ["GewichtKg", "WeightKg", "Gewicht", "Weight"]

REQUIRED_HEADERS = ["SKU", "Omschrijving", "Inkoopprijs", "Valuta", "GewichtKg"]


def validate_articles_csv(file_path: Path) -> ValidationResult:
    errors: list[ValidationError] = []
    warnings: list[ValidationWarning] = []

    # Parse (strict)
    rows = parse_csv(file_path)

    # Validate headers exist (using actual headers read)
    if rows:
        headers = list(rows[0].keys())
        require_headers(headers, REQUIRED_HEADERS, source=str(file_path))
    else:
        return ValidationResult(
            ok=False,
            errors=[
                _err(
                    "articles",
                    None,
                    None,
                    "EMPTY_FILE",
                    "Bestand bevat geen data-rijen.",
                )
            ],
            warnings=[],
        )

    seen_sku: set[str] = set()

    for idx, r in enumerate(rows):
        rownum = idx + 2  # header = 1

        sku_raw = to_str(get_cell(r, H_SKU))
        sku = sku_raw.strip().upper()
        if sku == "":
            errors.append(
                _err(
                    "articles",
                    rownum,
                    "SKU",
                    "REQUIRED",
                    "SKU is verplicht en mag niet leeg zijn.",
                )
            )
        else:
            if sku in seen_sku:
                errors.append(
                    _err(
                        "articles",
                        rownum,
                        "SKU",
                        "DUPLICATE",
                        f"SKU '{sku}' komt dubbel voor. Maak SKU uniek.",
                    )
                )
            seen_sku.add(sku)

        desc = to_str(get_cell(r, H_DESC))
        if desc == "":
            errors.append(
                _err(
                    "articles",
                    rownum,
                    "Omschrijving",
                    "REQUIRED",
                    "Omschrijving is verplicht en mag niet leeg zijn.",
                )
            )

        cur = to_str(get_cell(r, H_CUR)).upper()
        if cur == "":
            errors.append(
                _err("articles", rownum, "Valuta", "REQUIRED", "Valuta is verplicht.")
            )
        elif cur not in CURRENCY_WHITELIST:
            errors.append(
                _err(
                    "articles",
                    rownum,
                    "Valuta",
                    "NOT_ALLOWED",
                    f"Valuta '{cur}' is niet toegestaan. Toegestaan: {sorted(CURRENCY_WHITELIST)}",
                )
            )

        cost = to_decimal(
            get_cell(r, H_COST), source=f"{file_path}:{rownum}:Inkoopprijs"
        )
        if cost is None:
            errors.append(
                _err(
                    "articles",
                    rownum,
                    "Inkoopprijs",
                    "INVALID_NUMBER",
                    "Inkoopprijs moet een getal zijn (decimaal met ',').",
                )
            )
        elif cost < 0:
            errors.append(
                _err(
                    "articles",
                    rownum,
                    "Inkoopprijs",
                    "OUT_OF_RANGE",
                    "Inkoopprijs moet >= 0 zijn.",
                )
            )

        weight = to_decimal(
            get_cell(r, H_WEIGHT), source=f"{file_path}:{rownum}:GewichtKg"
        )
        if weight is None:
            errors.append(
                _err(
                    "articles",
                    rownum,
                    "GewichtKg",
                    "INVALID_NUMBER",
                    "GewichtKg moet een getal zijn (decimaal met ',').",
                )
            )
        elif weight <= 0:
            errors.append(
                _err(
                    "articles",
                    rownum,
                    "GewichtKg",
                    "OUT_OF_RANGE",
                    "GewichtKg moet > 0 zijn (geen 0, geen negatief).",
                )
            )

    return ValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)

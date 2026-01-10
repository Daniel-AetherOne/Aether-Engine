from __future__ import annotations

from pathlib import Path

from .common import (
    ValidationResult,
    ValidationError,
    ValidationWarning,
    _err,
    parse_csv,
    require_headers,
    get_cell,
    to_str,
    to_decimal,
)

H_SUP = ["Leverancier", "Supplier"]
H_FACTOR = ["Factor"]
H_CURPCT = ["ValutaOpslagPct", "CurrencyMarkupPct", "ValutaOpslag"]

REQUIRED_HEADERS = ["Leverancier", "Factor", "ValutaOpslagPct"]


def validate_supplier_factors_csv(file_path: Path) -> ValidationResult:
    errors: list[ValidationError] = []
    warnings: list[ValidationWarning] = []

    rows = parse_csv(file_path)

    if rows:
        headers = list(rows[0].keys())
        require_headers(headers, REQUIRED_HEADERS, source=str(file_path))
    else:
        return ValidationResult(
            ok=False,
            errors=[
                _err(
                    "supplier_factors",
                    None,
                    None,
                    "EMPTY_FILE",
                    "Bestand bevat geen data-rijen.",
                )
            ],
            warnings=[],
        )

    seen: set[str] = set()

    for idx, r in enumerate(rows):
        rownum = idx + 2

        sup = to_str(get_cell(r, H_SUP))
        key = sup.strip().lower()

        if sup == "":
            errors.append(
                _err(
                    "supplier_factors",
                    rownum,
                    "Leverancier",
                    "REQUIRED",
                    "Leverancier is verplicht.",
                )
            )
        else:
            if key in seen:
                errors.append(
                    _err(
                        "supplier_factors",
                        rownum,
                        "Leverancier",
                        "DUPLICATE",
                        f"Leverancier '{sup}' komt dubbel voor (case-insensitive).",
                    )
                )
            seen.add(key)

        factor = to_decimal(
            get_cell(r, H_FACTOR), source=f"{file_path}:{rownum}:Factor"
        )
        if factor is None:
            errors.append(
                _err(
                    "supplier_factors",
                    rownum,
                    "Factor",
                    "INVALID_NUMBER",
                    "Factor moet een getal zijn (> 0).",
                )
            )
        elif factor <= 0:
            errors.append(
                _err(
                    "supplier_factors",
                    rownum,
                    "Factor",
                    "OUT_OF_RANGE",
                    "Factor moet > 0 zijn.",
                )
            )

        pct = to_decimal(
            get_cell(r, H_CURPCT), source=f"{file_path}:{rownum}:ValutaOpslagPct"
        )
        if pct is None:
            errors.append(
                _err(
                    "supplier_factors",
                    rownum,
                    "ValutaOpslagPct",
                    "INVALID_NUMBER",
                    "ValutaOpslagPct moet een getal zijn (>= 0).",
                )
            )
        elif pct < 0:
            errors.append(
                _err(
                    "supplier_factors",
                    rownum,
                    "ValutaOpslagPct",
                    "OUT_OF_RANGE",
                    "ValutaOpslagPct moet >= 0 zijn.",
                )
            )

    return ValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)

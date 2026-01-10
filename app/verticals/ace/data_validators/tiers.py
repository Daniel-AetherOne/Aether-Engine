from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import (
    ValidationResult, ValidationError, ValidationWarning,
    _err, parse_csv, require_headers,
    get_cell, to_int, to_decimal
)

H_FROM = ["Van", "From"]
H_TO = ["Tot", "To"]
H_DISC = ["KortingPct", "DiscountPct", "Korting", "Discount"]

REQUIRED_HEADERS = ["Van", "Tot", "KortingPct"]


def validate_tiers_csv(file_path: Path) -> ValidationResult:
    errors: list[ValidationError] = []
    warnings: list[ValidationWarning] = []

    rows = parse_csv(file_path)

    if rows:
        headers = list(rows[0].keys())
        require_headers(headers, REQUIRED_HEADERS, source=str(file_path))
    else:
        return ValidationResult(ok=False, errors=[_err("tiers", None, None, "EMPTY_FILE", "Bestand bevat geen data-rijen.")], warnings=[])

    parsed: list[tuple[int, int | None, float, int]] = []  # (van, tot, korting, rownum)

    for idx, r in enumerate(rows):
        rownum = idx + 2

        v = to_int(get_cell(r, H_FROM))
        t = to_int(get_cell(r, H_TO))  # may be None (open-ended)
        k = to_decimal(get_cell(r, H_DISC), source=f"{file_path}:{rownum}:KortingPct")

        if v is None:
            errors.append(_err("tiers", rownum, "Van", "INVALID_INT", "Van moet een geheel getal zijn (>= 1)."))
            continue
        if v < 1:
            errors.append(_err("tiers", rownum, "Van", "OUT_OF_RANGE", "Van moet >= 1 zijn."))

        if t is not None and t < 1:
            errors.append(_err("tiers", rownum, "Tot", "OUT_OF_RANGE", "Tot moet >= 1 zijn (of leeg voor open-ended)."))

        if t is not None and v > t:
            errors.append(_err("tiers", rownum, "Tot", "INVALID_RANGE", "Van moet <= Tot zijn (als Tot bestaat)."))

        if k is None:
            errors.append(_err("tiers", rownum, "KortingPct", "INVALID_NUMBER", "KortingPct moet een getal zijn (0–100)."))
        else:
            if k < 0 or k > 100:
                errors.append(_err("tiers", rownum, "KortingPct", "OUT_OF_RANGE", "KortingPct moet tussen 0 en 100 liggen."))

        parsed.append((v, t, k if k is not None else 0.0, rownum))

    if errors:
        return ValidationResult(ok=False, errors=errors, warnings=warnings)

    # Sort and validate overlaps / coverage
    parsed.sort(key=lambda x: x[0])

    # coverage strict: must start at 1
    if parsed and parsed[0][0] != 1:
        errors.append(_err("tiers", parsed[0][3], "Van", "COVERAGE_GAP", "Eerste range moet starten bij Van=1 (geen gaten toegestaan)."))

    for i in range(len(parsed) - 1):
        v1, t1, _, r1 = parsed[i]
        v2, t2, _, r2 = parsed[i + 1]

        end1 = t1 if t1 is not None else None
        if end1 is None:
            errors.append(_err("tiers", r2, "Van", "OVERLAP", "Er staat een range na een open-ended range. Verwijder of corrigeer."))
            break

        # overlap check: next 'van' must be end1+1 (no gaps, no overlap)
        if v2 <= end1:
            errors.append(_err("tiers", r2, "Van", "OVERLAP", f"Ranges overlappen: vorige eindigt op {end1}, volgende start op {v2}."))
        elif v2 != end1 + 1:
            errors.append(_err("tiers", r2, "Van", "COVERAGE_GAP", f"Gap gevonden: vorige eindigt op {end1}, volgende start op {v2}. Geen gaten toegestaan."))

    return ValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)

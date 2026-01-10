from __future__ import annotations

from pathlib import Path

from .common import (
    ValidationResult, ValidationError, ValidationWarning,
    _err, parse_xlsx, require_headers,
    get_cell, to_str, to_decimal
)

H_ID = ["KlantID", "CustomerId", "CustomerID", "ID"]
H_PROFILE = ["Kortingsprofiel", "DiscountProfile", "Profiel", "Profile"]
H_MAX = ["MaxExtraKortingPct", "MaxExtraDiscountPct", "MaxExtraKorting"]

REQUIRED_HEADERS = ["KlantID", "Kortingsprofiel", "MaxExtraKortingPct"]

ALLOWED_PROFILES = {"STANDARD", "SILVER", "GOLD", "PLATINUM"}
MAX_EXTRA_DISCOUNT_LIMIT = 10.0


def validate_customers_xlsx(file_path: Path, *, sheet_name: str | None = None) -> ValidationResult:
    errors: list[ValidationError] = []
    warnings: list[ValidationWarning] = []

    rows = parse_xlsx(file_path, sheet_name=sheet_name)

    if rows:
        headers = list(rows[0].keys())
        require_headers(headers, REQUIRED_HEADERS, source=str(file_path))
    else:
        return ValidationResult(ok=False, errors=[_err("customers", None, None, "EMPTY_FILE", "Bestand bevat geen data-rijen.")], warnings=[])

    seen: set[str] = set()

    for idx, r in enumerate(rows):
        rownum = idx + 2

        cid = to_str(get_cell(r, H_ID))
        if cid == "":
            errors.append(_err("customers", rownum, "KlantID", "REQUIRED", "KlantID is verplicht."))
        else:
            key = cid.strip().lower()
            if key in seen:
                errors.append(_err("customers", rownum, "KlantID", "DUPLICATE", f"KlantID '{cid}' komt dubbel voor."))
            seen.add(key)

        prof = to_str(get_cell(r, H_PROFILE)).upper()
        if prof == "":
            errors.append(_err("customers", rownum, "Kortingsprofiel", "REQUIRED", "Kortingsprofiel is verplicht."))
        elif prof not in ALLOWED_PROFILES:
            errors.append(_err("customers", rownum, "Kortingsprofiel", "NOT_ALLOWED", f"Profiel '{prof}' is niet toegestaan. Toegestaan: {sorted(ALLOWED_PROFILES)}"))

        mx = to_decimal(get_cell(r, H_MAX), source=f"{file_path}:{rownum}:MaxExtraKortingPct")
        if mx is None:
            errors.append(_err("customers", rownum, "MaxExtraKortingPct", "INVALID_NUMBER", "MaxExtraKortingPct moet een getal zijn (0–10)."))
        else:
            if mx < 0:
                errors.append(_err("customers", rownum, "MaxExtraKortingPct", "OUT_OF_RANGE", "MaxExtraKortingPct moet >= 0 zijn."))
            if mx > MAX_EXTRA_DISCOUNT_LIMIT:
                errors.append(_err("customers", rownum, "MaxExtraKortingPct", "OUT_OF_RANGE", f"MaxExtraKortingPct mag niet hoger zijn dan {MAX_EXTRA_DISCOUNT_LIMIT}%."))

    return ValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)

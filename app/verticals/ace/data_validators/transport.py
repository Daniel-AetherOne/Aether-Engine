from __future__ import annotations

from pathlib import Path
import re

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

H_PC = ["Postcode", "PostalCode"]
H_ZONE = ["Zone"]
H_EURKG = ["EurPerKg", "EURPerKg", "€/kg"]

REQUIRED_HEADERS = ["Postcode", "Zone", "EurPerKg"]

# Strict NL: 1234AB or 1234 AB
NL_POSTCODE_RE = re.compile(r"^\d{4}\s?[A-Z]{2}$")


def normalize_postcode_nl(s: str) -> str:
    return s.strip().upper().replace(" ", "")


def validate_transport_csv(file_path: Path) -> ValidationResult:
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
                    "transport",
                    None,
                    None,
                    "EMPTY_FILE",
                    "Bestand bevat geen data-rijen.",
                )
            ],
            warnings=[],
        )

    seen_pc: set[str] = set()

    for idx, r in enumerate(rows):
        rownum = idx + 2

        pc_raw = to_str(get_cell(r, H_PC))
        pc_norm = normalize_postcode_nl(pc_raw)

        if pc_raw == "":
            errors.append(
                _err(
                    "transport",
                    rownum,
                    "Postcode",
                    "REQUIRED",
                    "Postcode is verplicht.",
                )
            )
        else:
            if not NL_POSTCODE_RE.match(pc_raw.strip().upper()):
                errors.append(
                    _err(
                        "transport",
                        rownum,
                        "Postcode",
                        "INVALID_FORMAT",
                        "Postcode moet NL formaat hebben: 1234AB of 1234 AB.",
                    )
                )
            else:
                if pc_norm in seen_pc:
                    errors.append(
                        _err(
                            "transport",
                            rownum,
                            "Postcode",
                            "DUPLICATE",
                            f"Postcode '{pc_norm}' komt dubbel voor. Duplicates zijn verboden.",
                        )
                    )
                seen_pc.add(pc_norm)

        zone = to_str(get_cell(r, H_ZONE))
        if zone == "":
            errors.append(
                _err(
                    "transport",
                    rownum,
                    "Zone",
                    "REQUIRED",
                    "Zone is verplicht en mag niet leeg zijn.",
                )
            )

        eurkg = to_decimal(
            get_cell(r, H_EURKG), source=f"{file_path}:{rownum}:EurPerKg"
        )
        if eurkg is None:
            errors.append(
                _err(
                    "transport",
                    rownum,
                    "EurPerKg",
                    "INVALID_NUMBER",
                    "EurPerKg moet een getal zijn (>= 0).",
                )
            )
        elif eurkg < 0:
            errors.append(
                _err(
                    "transport",
                    rownum,
                    "EurPerKg",
                    "OUT_OF_RANGE",
                    "EurPerKg moet >= 0 zijn.",
                )
            )

    return ValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)

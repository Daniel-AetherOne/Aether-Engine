from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import (
    ValidationResult,
    ValidationError,
    ValidationWarning,
    _err,
    _warn,
    ParseError,
    parse_csv,
    parse_xlsx,
    get_cell,
    to_str,
)
from .common import validate_dataset  # per-file (2.3)
from .profiles_config import ALLOWED_PROFILES, PROFILE_ALLOWED_ZONES
from .articles import CURRENCY_WHITELIST  # single source for MVP currencies


def validate_dataset_bundle(dataset_dir: Path) -> ValidationResult:
    """
    Cross-dataset coherence checks (no pricing logic).
    Runs:
      1) per-file schema validation (2.3) via validate_dataset()
      2) cross checks:
         - customers profiles exist in profiles_config
         - transport zones referenced exist (implicit from transport.csv)
         - currency whitelist consistent across datasets
    """
    base = validate_dataset(dataset_dir)

    # Als schema al faalt: cross-checks hebben weinig zin (en zouden extra noise geven)
    if not base.ok:
        return base

    errors: list[ValidationError] = list(base.errors)
    warnings: list[ValidationWarning] = list(base.warnings)

    # ---- Load minimal data (parsed rows) ----
    try:
        customers_rows = parse_xlsx(dataset_dir / "customers.xlsx")
    except ParseError as e:
        errors.append(_err("customers", None, None, "PARSE_ERROR", str(e)))
        return ValidationResult(ok=False, errors=errors, warnings=warnings)

    try:
        transport_rows = parse_csv(dataset_dir / "transport.csv")
    except ParseError as e:
        errors.append(_err("transport", None, None, "PARSE_ERROR", str(e)))
        return ValidationResult(ok=False, errors=errors, warnings=warnings)

    try:
        articles_rows = parse_csv(dataset_dir / "articles.csv")
    except ParseError as e:
        errors.append(_err("articles", None, None, "PARSE_ERROR", str(e)))
        return ValidationResult(ok=False, errors=errors, warnings=warnings)

    # ---- 2.4 Check 1: customers profiles exist in profiles_config ----
    # (Ook al enforce je dit in customers.py, dit is de cross-dataset “source of truth”.)
    H_PROFILE = ["Kortingsprofiel", "DiscountProfile", "Profiel", "Profile"]
    for i, r in enumerate(customers_rows):
        rownum = i + 2
        prof = to_str(get_cell(r, H_PROFILE)).upper()
        if prof and prof not in ALLOWED_PROFILES:
            errors.append(
                _err(
                    "customers",
                    rownum,
                    "Kortingsprofiel",
                    "UNKNOWN_PROFILE",
                    f"Kortingsprofiel '{prof}' bestaat niet in profiles_config. Toegestaan: {sorted(ALLOWED_PROFILES)}",
                )
            )

    # ---- 2.4 Check 2: transport zones referenced are valid ----
    # “Zone set is implicit from transport.csv”
    H_ZONE = ["Zone"]
    zone_set: set[str] = set()
    for r in transport_rows:
        z = to_str(get_cell(r, H_ZONE))
        if z:
            zone_set.add(z)

    # Als je PROFILE_ALLOWED_ZONES gebruikt: check dat alle zones die in config staan ook bestaan in transport.csv
    for profile, zones in PROFILE_ALLOWED_ZONES.items():
        for z in zones:
            if z not in zone_set:
                errors.append(
                    _err(
                        "transport",
                        None,
                        "Zone",
                        "UNKNOWN_ZONE",
                        f"profiles_config refereert zone '{z}' voor profiel '{profile}', maar die zone komt niet voor in transport.csv.",
                    )
                )

    # ---- 2.4 Check 3: valuta whitelist consistent ----
    # MVP: currencies staan in articles.csv. Supplier_factors heeft (nog) geen currency kolom.
    H_CUR = ["Valuta", "Currency"]
    currencies_seen: set[str] = set()
    for i, r in enumerate(articles_rows):
        rownum = i + 2
        c = to_str(get_cell(r, H_CUR)).upper()
        if c:
            currencies_seen.add(c)
            if c not in CURRENCY_WHITELIST:
                errors.append(
                    _err(
                        "articles",
                        rownum,
                        "Valuta",
                        "NOT_ALLOWED",
                        f"Valuta '{c}' is niet toegestaan. Toegestaan: {sorted(CURRENCY_WHITELIST)}",
                    )
                )

    # (Optional warning) als dataset meerdere valuta bevat — kan wenselijk of juist niet.
    if len(currencies_seen) > 1:
        warnings.append(
            _warn(
                "articles",
                None,
                "Valuta",
                "MULTI_CURRENCY",
                f"Meerdere valuta gevonden in articles.csv: {sorted(currencies_seen)}",
            )
        )

    return ValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)

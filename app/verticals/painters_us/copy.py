# app/verticals/painters_us/copy.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable


# -------------------------
# Helpers
# -------------------------


def _to_decimal(value: Any) -> Decimal:
    """
    Robust conversion to Decimal.
    Supports:
      - Decimal / int / float / str
      - Money-like objects with .amount (Decimal/str/float)
      - dict-like with {"amount": ...}
    """
    if value is None:
        return Decimal("0")

    if isinstance(value, Decimal):
        return value

    if isinstance(value, (int, float)):
        return Decimal(str(value))

    if isinstance(value, str):
        # strip $ and commas if any
        v = value.strip().replace("$", "").replace(",", "")
        if v == "":
            return Decimal("0")
        return Decimal(v)

    # Money-like: .amount
    amount = getattr(value, "amount", None)
    if amount is not None:
        return _to_decimal(amount)

    # dict-like: ["amount"]
    if isinstance(value, dict) and "amount" in value:
        return _to_decimal(value.get("amount"))

    # fallback
    return Decimal(str(value))


def fmt_qty(quantity: float | int | Decimal, unit: str = "") -> str:
    """
    Logical qty formatting:
      - no '12.0000'
      - keeps 2 decimals only when needed
    Examples:
      12 -> "12"
      12.5 -> "12.5"
      12.34 -> "12.34"
    """
    d = _to_decimal(quantity)

    # If it's effectively an integer -> no decimals
    if d == d.to_integral_value():
        return f"{int(d)}"

    # Otherwise keep up to 2 decimals, trim trailing zeros
    d2 = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    s = f"{d2:f}"  # no scientific notation
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


# -------------------------
# Money formatting (USD)
# -------------------------


def fmt_usd(amount: Any) -> str:
    """
    Format amount as US dollars with 2 decimals.
    Supports Money objects and dicts with {amount: ...}.
    Examples: 1200 -> "$1,200.00", 99.5 -> "$99.50"
    """
    d = _to_decimal(amount)
    d = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"${d:,.2f}"


def fmt_usd_range(low: Any, high: Any) -> str:
    """
    Format a USD range: "$X.XX – $Y.XX"
    """
    return f"{fmt_usd(low)} – {fmt_usd(high)}"


# -------------------------
# Guardrails (Terminology)
# -------------------------

FORBIDDEN_TERMS: tuple[str, ...] = (
    "quote",
    "quotation",
    "proposal",
    "offer",
    "bid",
    "offerte",
    "vat",
    "btw",
)


def assert_no_forbidden_terms(
    text: str, *, extra_forbidden: Iterable[str] = ()
) -> None:
    hay = text.lower()
    forbidden = list(FORBIDDEN_TERMS) + [t.lower() for t in extra_forbidden]
    hits = [t for t in forbidden if t and t in hay]
    if hits:
        raise ValueError(f"Forbidden terminology found in output: {sorted(set(hits))}")


# -------------------------
# Copy model
# -------------------------


@dataclass(frozen=True)
class EstimateCopy:
    doc_type: str
    doc_title: str

    estimate_word: str
    needs_review_badge: str

    labor_label: str
    materials_label: str
    scope_label: str
    surfaces_label: str
    assumptions_label: str
    exclusions_label: str

    validity_copy: str
    subject_to_verification_copy: str

    estimated_total_label: str
    estimated_total_range_label: str

    opener_pricing_ready: str
    opener_needs_review: str

    disclaimer_pricing_ready: str
    disclaimer_needs_review: str

    cta_review: str
    cta_request_changes: str
    cta_approve: str

    currency_code: str
    currency_symbol: str


US_PAINTERS_ESTIMATE_COPY = EstimateCopy(
    doc_type="estimate",
    doc_title="Painting Estimate",
    estimate_word="Estimate",
    needs_review_badge="Estimate Needs Review",
    labor_label="Labor",
    materials_label="Materials",
    scope_label="Scope of Work",
    surfaces_label="Surfaces Included",
    assumptions_label="Assumptions",
    exclusions_label="Exclusions",
    validity_copy="Valid for {days} days from issue date.",
    subject_to_verification_copy="Subject to on-site verification.",
    estimated_total_label="Estimated Total",
    estimated_total_range_label="Estimated Total Range",
    opener_pricing_ready=(
        "This Estimate is based on the photos/details provided and typical site conditions. "
        "Final pricing may adjust if on-site conditions differ from what's visible."
    ),
    opener_needs_review=(
        "This Estimate Needs Review because one or more areas couldn’t be priced with high confidence "
        "from the provided photos/details. The range below is provisional until verified."
    ),
    disclaimer_pricing_ready=(
        "Estimate is subject to site verification, final measurements, surface conditions, and scope changes. "
        "Hidden damage (e.g., rot, moisture, peeling beneath layers) may require additional prep. "
        "Scheduling is subject to availability and weather. Sales tax may apply where required. "
        "This document is an estimate only and is not an invoice."
    ),
    disclaimer_needs_review=(
        "This estimate range is preliminary and subject to review due to incomplete visibility/uncertainty in the provided inputs. "
        "A site visit or additional photos may be required to confirm prep level, access constraints, and exact quantities. "
        "Sales tax may apply where required. This document is an estimate only and is not an invoice."
    ),
    cta_review="Review estimate",
    cta_request_changes="Request revisions",
    cta_approve="Approve estimate",
    currency_code="USD",
    currency_symbol="$",
)

# app/verticals/painters_us/copy.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable


# -------------------------
# Money formatting (USD)
# -------------------------


def fmt_usd(amount: float | int | Decimal) -> str:
    """
    Format amount as US dollars with 2 decimals.
    Examples: 1200 -> "$1,200.00", 99.5 -> "$99.50"
    """
    d = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    d = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    # Use Python's locale-independent comma grouping:
    return f"${d:,.2f}"


def fmt_usd_range(low: float | int | Decimal, high: float | int | Decimal) -> str:
    """
    Format a USD range: "$X.XX – $Y.XX"
    """
    return f"{fmt_usd(low)} – {fmt_usd(high)}"


# -------------------------
# Guardrails (Terminology)
# -------------------------

FORBIDDEN_TERMS: tuple[str, ...] = (
    # "Quote" synonyms / legal-ish docs we do NOT want in US output
    "quote",
    "quotation",
    "proposal",
    "offer",
    "bid",
    "offerte",
    # tax acronyms we do NOT want to show as VAT/BTW (EU language)
    "vat",
    "btw",
)


def assert_no_forbidden_terms(
    text: str, *, extra_forbidden: Iterable[str] = ()
) -> None:
    """
    Simple QA guard: raise if forbidden terms appear (case-insensitive).
    Useful for unit tests on rendered HTML/PDF text.
    """
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
    # Document identity
    doc_type: str
    doc_title: str

    # Core labels
    estimate_word: str
    needs_review_badge: str

    labor_label: str
    materials_label: str
    scope_label: str
    surfaces_label: str
    assumptions_label: str
    exclusions_label: str

    # Totals labels (must communicate "estimate")
    estimated_total_label: str
    estimated_total_range_label: str

    # Openers (framing)
    opener_pricing_ready: str
    opener_needs_review: str

    # Disclaimers (professional US style)
    disclaimer_pricing_ready: str
    disclaimer_needs_review: str

    # CTA language (optional but helps keep UI consistent)
    cta_review: str
    cta_request_changes: str
    cta_approve: str

    # Meta
    currency_code: str
    currency_symbol: str


US_PAINTERS_ESTIMATE_COPY = EstimateCopy(
    # Identity
    doc_type="estimate",
    doc_title="Painting Estimate",
    # Core words
    estimate_word="Estimate",
    needs_review_badge="Estimate Needs Review",
    # Section labels
    labor_label="Labor",
    materials_label="Materials",
    scope_label="Scope of Work",
    surfaces_label="Surfaces Included",
    assumptions_label="Assumptions",
    exclusions_label="Exclusions",
    # Total labels
    estimated_total_label="Estimated Total",
    estimated_total_range_label="Estimated Total Range",
    # Framing
    opener_pricing_ready=(
        "This Estimate is based on the photos/details provided and typical site conditions. "
        "Final pricing may adjust if on-site conditions differ from what’s visible."
    ),
    opener_needs_review=(
        "This Estimate Needs Review because one or more areas couldn’t be priced with high confidence "
        "from the provided photos/details. The range below is provisional until verified."
    ),
    # Disclaimers
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
    # CTAs
    cta_review="Review estimate",
    cta_request_changes="Request revisions",
    cta_approve="Approve estimate",
    # Currency
    currency_code="USD",
    currency_symbol="$",
)

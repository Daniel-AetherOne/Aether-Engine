from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

MONEY = Decimal("0.01")


def _d(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def qmoney(x) -> Decimal:
    return _d(x).quantize(MONEY, rounding=ROUND_HALF_UP)


def fmt_eur(amount, symbol: str = "€") -> str:
    """
    2450.5 -> "€ 2.450,50"
    """
    d = qmoney(amount)
    s = f"{d:.2f}"
    whole, frac = s.split(".")
    # group thousands with "."
    parts = []
    while whole:
        parts.append(whole[-3:])
        whole = whole[:-3]
    whole = ".".join(reversed(parts))
    return f"{symbol} {whole},{frac}"


@dataclass(frozen=True)
class VatTotals:
    subtotal_excl_vat: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    total_incl_vat: Decimal


def calc_vat(subtotal_excl_vat, vat_rate) -> VatTotals:
    subtotal = qmoney(subtotal_excl_vat)
    rate = _d(vat_rate)
    vat_amount = qmoney(subtotal * rate)
    total = qmoney(subtotal + vat_amount)
    return VatTotals(
        subtotal_excl_vat=subtotal,
        vat_rate=rate,
        vat_amount=vat_amount,
        total_incl_vat=total,
    )

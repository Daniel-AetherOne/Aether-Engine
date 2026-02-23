from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

MONEY = Decimal("0.01")

def qmoney(x: Decimal) -> Decimal:
    return x.quantize(MONEY, rounding=ROUND_HALF_UP)

@dataclass(frozen=True)
class VatBreakdown:
    subtotal_excl_vat: Decimal
    vat_rate: Decimal
    vat_amount: Decimal
    total_incl_vat: Decimal

def calc_vat(subtotal_excl_vat: Decimal, vat_rate: Decimal) -> VatBreakdown:
    subtotal = qmoney(Decimal(subtotal_excl_vat))
    rate = Decimal(vat_rate)
    vat_amount = qmoney(subtotal * rate)
    total = qmoney(subtotal + vat_amount)
    return VatBreakdown(subtotal, rate, vat_amount, total)
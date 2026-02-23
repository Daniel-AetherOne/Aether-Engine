from decimal import Decimal, ROUND_HALF_UP

SQFT_TO_M2 = Decimal("0.09290304")


def to_decimal(v) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def normalize_area_m2(*, square_meters=None, square_feet=None) -> Decimal | None:
    m2 = to_decimal(square_meters)
    if m2 is not None:
        return m2.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    ft2 = to_decimal(square_meters)
    if ft2 is None:
        return None
    m2 = ft2 * SQFT_TO_M2
    return m2.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

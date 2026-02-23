from decimal import Decimal

def format_number_eu(value: Decimal | str | float, decimal_sep=",", thousand_sep=".") -> str:
    # simpele formatter: 12345.67 -> 12.345,67
    d = Decimal(str(value))
    s = f"{d:.2f}"
    whole, frac = s.split(".")
    # thousand grouping
    parts = []
    while whole:
        parts.append(whole[-3:])
        whole = whole[:-3]
    whole = thousand_sep.join(reversed(parts))
    return f"{whole}{decimal_sep}{frac}"

def format_money(value, currency_symbol="€", decimal_sep=",", thousand_sep=".") -> str:
    return f"{currency_symbol} {format_number_eu(value, decimal_sep, thousand_sep)}"

def format_area_m2(value) -> str:
    d = Decimal(str(value))
    return f"{d:.2f} m²"
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class Country(StrEnum):
    NL = "NL"
    BE = "BE"
    DE = "DE"
    SE = "SE"
    NO = "NO"
    DK = "DK"
    FI = "FI"


class Currency(StrEnum):
    EUR = "EUR"
    SEK = "SEK"
    NOK = "NOK"
    DKK = "DKK"


@dataclass(frozen=True)
class CountryConfig:
    country: Country
    currency: Currency
    vat_rate: Decimal  # 0.09 means 9%
    timezone: str  # IANA tz e.g. "Europe/Amsterdam"
    decimal_sep: str  # "," for EU
    thousand_sep: str  # "."
    currency_symbol: str  # "€" etc


EU_COUNTRY_CONFIG: dict[Country, CountryConfig] = {
    Country.NL: CountryConfig(
        Country.NL, Currency.EUR, Decimal("0.09"), "Europe/Amsterdam", ",", ".", "€"
    ),
    Country.BE: CountryConfig(
        Country.BE, Currency.EUR, Decimal("0.06"), "Europe/Brussels", ",", ".", "€"
    ),
    Country.DE: CountryConfig(
        Country.DE, Currency.EUR, Decimal("0.19"), "Europe/Berlin", ",", ".", "€"
    ),
    # Scandinavië: VAT alvast 25% als default, currency later “niet-prioriteit” maar kan al klaarstaan
    Country.SE: CountryConfig(
        Country.SE, Currency.SEK, Decimal("0.25"), "Europe/Stockholm", ",", " ", "kr"
    ),
    Country.NO: CountryConfig(
        Country.NO, Currency.NOK, Decimal("0.25"), "Europe/Oslo", ",", " ", "kr"
    ),
    Country.DK: CountryConfig(
        Country.DK, Currency.DKK, Decimal("0.25"), "Europe/Copenhagen", ",", ".", "kr"
    ),
    Country.FI: CountryConfig(
        Country.FI, Currency.EUR, Decimal("0.25"), "Europe/Helsinki", ",", " ", "€"
    ),
}

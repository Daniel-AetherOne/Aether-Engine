from decimal import Decimal
from app.domain.geo import Country, EU_COUNTRY_CONFIG, CountryConfig

def resolve_country(lead_country: str | None, tenant_country: str) -> Country:
    raw = (lead_country or tenant_country or "NL").upper()
    return Country(raw)

def get_country_config(country: Country) -> CountryConfig:
    return EU_COUNTRY_CONFIG[country]

def enrich_lead_eu_fields(*, lead, tenant) -> None:
    country = resolve_country(lead.country, tenant.default_country)
    cfg = get_country_config(country)

    lead.country = country.value
    lead.currency = cfg.currency.value
    lead.vat_rate = Decimal(cfg.vat_rate)   # keep Decimal
    # lead timezone: lead override > tenant default > cfg default
    lead.timezone = lead.timezone or tenant.default_timezone or cfg.timezone
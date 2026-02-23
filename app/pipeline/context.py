from dataclasses import dataclass
from app.domain.geo import CountryConfig
from app.services.tax import VatBreakdown

@dataclass
class PipelineContext:
    tenant_id: str
    lead_id: str
    country_config: CountryConfig
    vat: VatBreakdown | None = None
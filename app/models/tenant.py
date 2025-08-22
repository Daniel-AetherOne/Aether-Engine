from pydantic import BaseModel, Field
from typing import Optional

class TenantSettings(BaseModel):
    """Tenant configuration settings"""
    tenant_id: str = Field(..., description="Unique tenant identifier")
    company_name: str = Field(..., description="Company name for branding")
    logo_url: Optional[str] = Field(None, description="URL to company logo")
    hubspot_token: Optional[str] = Field(None, description="HubSpot API token")
    pipeline: Optional[str] = Field(None, description="HubSpot pipeline name")
    stage: Optional[str] = Field(None, description="HubSpot stage name")
    primary_color: Optional[str] = Field("#2563eb", description="Primary brand color")
    secondary_color: Optional[str] = Field("#64748b", description="Secondary brand color")
    
    class Config:
        json_schema_extra = {
            "example": {
                "tenant_id": "company_a",
                "company_name": "Company A B.V.",
                "logo_url": "https://example.com/logo.png",
                "hubspot_token": "pat-xxx",
                "pipeline": "Default Pipeline",
                "stage": "New Lead",
                "primary_color": "#2563eb",
                "secondary_color": "#64748b"
            }
        }

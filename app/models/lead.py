from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime
import uuid

class Lead(BaseModel):
    """Lead model for tracking customer leads"""
    lead_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique lead identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    name: str = Field(..., min_length=1, description="Customer name")
    email: EmailStr = Field(..., description="Customer email address")
    phone: str = Field(..., min_length=1, description="Customer phone number")
    address: str = Field(..., min_length=1, description="Customer address")
    square_meters: float = Field(..., gt=0, description="Square meters")
    uploaded_files: List[str] = Field(default_factory=list, description="List of uploaded file paths")
    submission_date: datetime = Field(default_factory=datetime.utcnow, description="Lead submission date")
    status: str = Field("new", description="Lead status")
    notes: Optional[str] = Field(None, description="Additional notes")
    
    class Config:
        json_schema_extra = {
            "example": {
                "tenant_id": "company_a",
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "+31 6 12345678",
                "address": "Hoofdstraat 123, Amsterdam",
                "square_meters": 150.5,
                "status": "new",
                "notes": "Interested in renovation project"
            }
        }

class LeadCreate(BaseModel):
    """Model for creating a new lead"""
    tenant_id: str = Field(..., description="Tenant identifier")
    name: str = Field(..., min_length=1, description="Customer name")
    email: EmailStr = Field(..., description="Customer email address")
    phone: str = Field(..., min_length=1, description="Customer phone number")
    address: str = Field(..., min_length=1, description="Customer address")
    square_meters: float = Field(..., gt=0, description="Square meters")
    notes: Optional[str] = Field(None, description="Additional notes")

class LeadUpdate(BaseModel):
    """Model for updating a lead"""
    name: Optional[str] = Field(None, min_length=1, description="Customer name")
    email: Optional[EmailStr] = Field(None, description="Customer email address")
    phone: Optional[str] = Field(None, min_length=1, description="Customer phone number")
    address: Optional[str] = Field(None, min_length=1, description="Customer address")
    square_meters: Optional[float] = Field(None, gt=0, description="Square meters")
    status: Optional[str] = Field(None, description="Lead status")
    notes: Optional[str] = Field(None, description="Additional notes")

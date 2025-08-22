from pydantic import BaseModel, EmailStr, Field, validator
from typing import List, Optional
from datetime import datetime
import uuid

class IntakeRequest(BaseModel):
    """Request model for intake form data"""
    name: str = Field(..., min_length=1, description="Customer name")
    email: EmailStr = Field(..., description="Customer email address")
    phone: str = Field(..., min_length=1, description="Customer phone number")
    address: str = Field(..., min_length=1, description="Customer address")
    square_meters: float = Field(..., gt=0, description="Square meters (must be greater than 0)")
    tenant_id: str = Field(..., description="Tenant identifier")
    
    @validator('square_meters')
    def validate_square_meters(cls, v):
        if v <= 0:
            raise ValueError('Square meters must be greater than 0')
        return v

class IntakeResponse(BaseModel):
    """Response model for intake submission"""
    lead_id: str
    tenant_id: str
    name: str
    email: str
    phone: str
    address: str
    square_meters: float
    uploaded_files: List[str]
    submission_date: datetime
    status: str = "submitted"

class IntakeFormData(BaseModel):
    """Form data for the intake form"""
    name: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    square_meters: str = ""
    tenant_id: str = ""
    error_message: Optional[str] = None




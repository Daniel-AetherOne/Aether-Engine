from pydantic import BaseModel, Field
from typing import List, Dict

class PredictRequest(BaseModel):
    """Request model for prediction endpoint"""
    lead_id: str = Field(..., description="Unique identifier for the lead")
    tenant_id: str = Field(..., description="Tenant identifier")
    image_paths: List[str] = Field(..., description="List of paths to uploaded images")
    m2: float = Field(..., gt=0, description="Square meters of the area (must be greater than 0)")

class PredictResponse(BaseModel):
    """Response model for prediction endpoint"""
    lead_id: str = Field(..., description="Unique identifier for the lead")
    tenant_id: str = Field(..., description="Tenant identifier")
    substrate: str = Field(..., description="Predicted substrate type")
    issues: List[str] = Field(..., description="List of detected issues")
    confidences: Dict[str, float] = Field(..., description="Confidence scores for predictions")

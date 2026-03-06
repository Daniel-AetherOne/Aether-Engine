from pydantic import BaseModel, Field
from typing import Literal, List, Dict, Optional

Level3 = Literal["low", "medium", "high"]


class SignalEvidence(BaseModel):
    key: str
    value: str | float | int | bool
    confidence: float = Field(ge=0.0, le=1.0)
    source: str = "vision"  # or "intake", "rule"


class PaintlyVisionDecisionVars(BaseModel):
    prep_level: Level3 = "medium"
    complexity: Level3 = "medium"
    access_risk: Level3 = "medium"


class ConfidenceBundle(BaseModel):
    prep_conf: float = Field(ge=0.0, le=1.0)
    complexity_conf: float = Field(ge=0.0, le=1.0)
    access_conf: float = Field(ge=0.0, le=1.0)
    overall: float = Field(ge=0.0, le=1.0)


class PricingInputs(BaseModel):
    estimated_area_m2: float
    vars: PaintlyVisionDecisionVars
    confidence: ConfidenceBundle
    evidences: List[SignalEvidence] = []
    needs_review: bool = False
    review_reasons: List[str] = []

from sqlalchemy import Column, String, Float, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.db.base import Base


class PredictionSnapshot(Base):
    __tablename__ = "prediction_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # voorspellingen
    predicted_price_total = Column(Float, nullable=True)
    predicted_labor_hours = Column(Float, nullable=True)
    predicted_material_cost = Column(Float, nullable=True)

    # metadata
    pricing_strategy = Column(String, nullable=True)  # rules_v1, hybrid_v1
    pricing_version = Column(String, nullable=True)
    confidence_score = Column(Float, nullable=True)

    # volledige payload
    features_json = Column(JSON, nullable=True)
    prediction_json = Column(JSON, nullable=True)

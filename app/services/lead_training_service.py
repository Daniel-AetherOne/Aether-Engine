from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import LeadTrainingRecord

logger = logging.getLogger(__name__)


def _to_json_safe(value: Any) -> Any:
    """Recursively convert payloads to JSON-serializable primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(k): _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_json_safe(v) for v in value]
    # Fallback for custom objects
    return str(value)


def capture_ml_data(
    db: Session,
    *,
    tenant_id: str,
    lead_id: str,
    intake_snapshot: Optional[Dict[str, Any]] = None,
    photo_refs: Optional[List[Dict[str, Any]]] = None,
    estimate_input: Optional[Dict[str, Any]] = None,
    estimate_output: Optional[Dict[str, Any]] = None,
    pricing_result: Optional[Dict[str, Any]] = None,
    metadata_json: Optional[Dict[str, Any]] = None,
) -> LeadTrainingRecord:
    """
    Create or update a LeadTrainingRecord snapshot for a given tenant/lead.

    This function does not commit the transaction; callers are responsible
    for committing or rolling back on the provided Session.
    """
    record = (
        db.query(LeadTrainingRecord)
        .filter(
            LeadTrainingRecord.tenant_id == tenant_id,
            LeadTrainingRecord.lead_id == lead_id,
        )
        .one_or_none()
    )

    if record is None:
        record = LeadTrainingRecord(
            tenant_id=tenant_id,
            lead_id=lead_id,
        )
        db.add(record)

    safe_payloads: Dict[str, Any] = {}
    for field_name, field_value in {
        "intake_snapshot": intake_snapshot,
        "photo_refs": photo_refs,
        "estimate_input": estimate_input,
        "estimate_output": estimate_output,
        "pricing_result": pricing_result,
        "metadata_json": metadata_json,
    }.items():
        try:
            safe_payloads[field_name] = _to_json_safe(field_value)
        except Exception:
            logger.exception(
                "LEAD_TRAINING_SERIALIZE_FAILED tenant_id=%s lead_id=%s field=%s",
                tenant_id,
                lead_id,
                field_name,
            )
            safe_payloads[field_name] = str(field_value)

    record.intake_snapshot = safe_payloads["intake_snapshot"]
    record.photo_refs = safe_payloads["photo_refs"]
    record.estimate_input = safe_payloads["estimate_input"]
    record.estimate_output = safe_payloads["estimate_output"]
    record.pricing_result = safe_payloads["pricing_result"]
    record.metadata_json = safe_payloads["metadata_json"]

    # SQLAlchemy will handle updated_at via onupdate=func.now() on flush/commit.
    try:
        db.flush()
    except Exception:
        db.rollback()
        logger.exception(
            "LEAD_TRAINING_FLUSH_FAILED tenant_id=%s lead_id=%s keys=%s",
            tenant_id,
            lead_id,
            list(safe_payloads.keys()),
        )
        raise

    return record


def update_capture_outcome(
    db: Session,
    *,
    tenant_id: str,
    lead_id: str,
    outcome: Optional[str] = None,
    outcome_reason: Optional[str] = None,
) -> Optional[LeadTrainingRecord]:
    """
    Update outcome fields on an existing LeadTrainingRecord.

    Returns the updated record or None if no record exists for the key.
    """
    record = (
        db.query(LeadTrainingRecord)
        .filter(
            LeadTrainingRecord.tenant_id == tenant_id,
            LeadTrainingRecord.lead_id == lead_id,
        )
        .one_or_none()
    )

    if record is None:
        return None

    record.outcome = outcome
    record.outcome_reason = outcome_reason

    db.flush()

    return record


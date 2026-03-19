from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import LeadTrainingRecord


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

    record.intake_snapshot = intake_snapshot
    record.photo_refs = photo_refs
    record.estimate_input = estimate_input
    record.estimate_output = estimate_output
    record.pricing_result = pricing_result
    record.metadata_json = metadata_json

    # SQLAlchemy will handle updated_at via onupdate=func.now() on flush/commit.
    db.flush()

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


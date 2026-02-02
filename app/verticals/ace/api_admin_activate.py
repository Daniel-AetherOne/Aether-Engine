from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException

from app.verticals.ace.api.dependencies.admin_auth import require_admin
from app.verticals.ace.domain.auth import AdminIdentity
from app.verticals.ace.audit.logger import audit_logger, AuditWrite

from app.verticals.ace.data_validators import validate_dataset_bundle
from app.verticals.ace.storage.loader import (
    staging_dataset_dir,
    activate_staging_dataset,
)

router = APIRouter(prefix="/admin/datasets", tags=["datasets-admin"])


@router.post("/activate/{dataset_id}")
def activate_dataset(
    dataset_id: str,
    admin: AdminIdentity = Depends(require_admin),
):
    ds = staging_dataset_dir(dataset_id)

    res = validate_dataset_bundle(ds)
    if not res.ok:
        audit_logger.log(
            AuditWrite(
                action_type="DATASET_ACTIVATE_FAILED",
                actor=admin,
                target_type="DATASET_STAGING",
                target_id=dataset_id,
                meta={
                    "dataset_id": dataset_id,
                    "errors": [e.__dict__ for e in res.errors],
                    "warnings": [w.__dict__ for w in res.warnings],
                },
                audit_id=f"dataset_activate_failed:{dataset_id}:{uuid.uuid4().hex}",
            )
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validation failed; cannot activate dataset.",
                "errors": [e.__dict__ for e in res.errors],
                "warnings": [w.__dict__ for w in res.warnings],
            },
        )

    act = activate_staging_dataset(dataset_id)
    if not act.ok:
        audit_logger.log(
            AuditWrite(
                action_type="DATASET_ACTIVATE_ERROR",
                actor=admin,
                target_type="DATASET_STAGING",
                target_id=dataset_id,
                meta={"dataset_id": dataset_id, "message": act.message},
                audit_id=f"dataset_activate_error:{dataset_id}:{uuid.uuid4().hex}",
            )
        )
        raise HTTPException(status_code=500, detail={"message": act.message})

    audit_logger.log_deduped(
        AuditWrite(
            action_type="DATASET_ACTIVATED",
            actor=admin,
            target_type="DATASET",
            target_id=act.new_dataset_id,
            old_value={"previous_archived_id": act.previous_archived_id},
            new_value={"active_version_id": act.new_dataset_id},
            meta={
                "dataset_id": dataset_id,
                "activated_dataset_id": act.new_dataset_id,
                "previous_archived_id": act.previous_archived_id,
            },
            audit_id=f"dataset_activated:{dataset_id}:{act.new_dataset_id}",
        )
    )

    return {
        "ok": True,
        "activatedDatasetId": act.new_dataset_id,
        "previousArchivedId": act.previous_archived_id,
        "message": act.message,
    }

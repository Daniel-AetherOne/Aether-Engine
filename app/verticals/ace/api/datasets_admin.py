from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException, Query

from app.verticals.ace.api.dependencies.admin_auth import require_admin
from app.verticals.ace.domain.auth import AdminIdentity
from app.verticals.ace.audit.logger import audit_logger, AuditWrite

from app.verticals.ace.data_validators import validate_dataset_bundle
from app.verticals.ace.storage.loader import (
    staging_dataset_dir,
    activate_staging_dataset,
    rollback_to_version,
    archive_dataset_dir,
)

router = APIRouter(prefix="/admin/datasets", tags=["datasets-admin"])


@router.post("/activate/{dataset_id}")
def activate_dataset(
    dataset_id: str,
    admin: AdminIdentity = Depends(require_admin),
):
    # 7.8 HARD GATE: audit must succeed before anything else
    attempt_id = f"data_activate_attempt:{dataset_id}:{uuid.uuid4().hex}"
    audit_logger.log(
        AuditWrite(
            action_type="DATA_ACTIVATE_ATTEMPT",
            actor=admin,
            target_type="DATASET",
            target_id=dataset_id,
            meta={"dataset_id": dataset_id},
            audit_id=attempt_id,
        )
    )

    ds = staging_dataset_dir(dataset_id)

    res = validate_dataset_bundle(ds)
    if not res.ok:
        audit_logger.log(
            AuditWrite(
                action_type="DATA_ACTIVATE",
                actor=admin,
                target_type="DATASET",
                target_id=dataset_id,
                meta={
                    "attempt_id": attempt_id,
                    "outcome": "failed_validation",
                    "dataset_id": dataset_id,
                    "errors": [e.__dict__ for e in res.errors],
                    "warnings": [w.__dict__ for w in res.warnings],
                },
                audit_id=f"data_activate_failed:{dataset_id}:{uuid.uuid4().hex}",
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

    act = activate_staging_dataset(dataset_id, uploaded_by=admin.username)
    if not act.ok:
        audit_logger.log(
            AuditWrite(
                action_type="DATA_ACTIVATE",
                actor=admin,
                target_type="DATASET",
                target_id=dataset_id,
                meta={
                    "attempt_id": attempt_id,
                    "outcome": "error",
                    "dataset_id": dataset_id,
                    "message": act.message,
                },
                audit_id=f"data_activate_error:{dataset_id}:{uuid.uuid4().hex}",
            )
        )
        raise HTTPException(status_code=500, detail={"message": act.message})

    audit_logger.log_deduped(
        AuditWrite(
            action_type="DATA_ACTIVATE",
            actor=admin,
            target_type="DATASET",
            target_id=dataset_id,
            old_value={"previousArchivedId": act.previous_archived_id},
            new_value={"activeVersionId": act.new_dataset_id},
            meta={
                "attempt_id": attempt_id,
                "outcome": "ok",
                "dataset_id": dataset_id,
                "activeVersionId": act.new_dataset_id,
                "previousArchivedId": act.previous_archived_id,
            },
            audit_id=f"data_activated:{dataset_id}:{act.new_dataset_id}",
        )
    )

    return {
        "ok": True,
        "activeVersionId": act.new_dataset_id,
        "previousArchivedId": act.previous_archived_id,
        "message": act.message,
    }


@router.post("/rollback/{version_id}")
def rollback_dataset(
    version_id: str,
    reason: str = Query(..., min_length=3),
    admin: AdminIdentity = Depends(require_admin),
):
    # 7.8 HARD GATE: audit must succeed before anything else
    attempt_id = f"data_rollback_attempt:{version_id}:{uuid.uuid4().hex}"
    audit_logger.log(
        AuditWrite(
            action_type="DATA_ROLLBACK_ATTEMPT",
            actor=admin,
            target_type="DATASET",
            target_id=version_id,
            reason=reason,  # reason required by audit policy
            meta={"version_id": version_id},
            audit_id=attempt_id,
        )
    )

    ds = archive_dataset_dir(version_id)

    res = validate_dataset_bundle(ds)
    if not res.ok:
        audit_logger.log(
            AuditWrite(
                action_type="DATA_ROLLBACK",
                actor=admin,
                target_type="DATASET",
                target_id=version_id,
                reason=reason,
                meta={
                    "attempt_id": attempt_id,
                    "outcome": "failed_validation",
                    "version_id": version_id,
                    "errors": [e.__dict__ for e in res.errors],
                    "warnings": [w.__dict__ for w in res.warnings],
                },
                audit_id=f"data_rollback_failed:{version_id}:{uuid.uuid4().hex}",
            )
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validation failed; cannot rollback to this version.",
                "errors": [e.__dict__ for e in res.errors],
                "warnings": [w.__dict__ for w in res.warnings],
            },
        )

    rb = rollback_to_version(version_id, uploaded_by=admin.username)
    if not rb.ok:
        audit_logger.log(
            AuditWrite(
                action_type="DATA_ROLLBACK",
                actor=admin,
                target_type="DATASET",
                target_id=version_id,
                reason=reason,
                meta={
                    "attempt_id": attempt_id,
                    "outcome": "error",
                    "version_id": version_id,
                    "message": rb.message,
                },
                audit_id=f"data_rollback_error:{version_id}:{uuid.uuid4().hex}",
            )
        )
        raise HTTPException(status_code=500, detail={"message": rb.message})

    audit_logger.log_deduped(
        AuditWrite(
            action_type="DATA_ROLLBACK",
            actor=admin,
            target_type="DATASET",
            target_id=version_id,
            reason=reason,
            old_value={"activeBefore": rb.previous_archived_id},
            new_value={"activeAfter": rb.new_dataset_id},
            meta={
                "attempt_id": attempt_id,
                "outcome": "ok",
                "version_id": version_id,
                "activeVersionId": rb.new_dataset_id,
                "previousArchivedId": rb.previous_archived_id,
            },
            audit_id=f"data_rolled_back:{version_id}:{rb.new_dataset_id}",
        )
    )

    return {
        "ok": True,
        "activeVersionId": rb.new_dataset_id,
        "previousArchivedId": rb.previous_archived_id,
        "message": rb.message,
    }

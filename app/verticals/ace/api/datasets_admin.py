from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException

from app.verticals.ace.api.dependencies.admin_auth import require_admin
from app.verticals.ace.domain.auth import AdminIdentity
from app.verticals.ace.audit_log import AuditLog, audit_db_path

from app.verticals.ace.data_validators import validate_dataset_bundle
from app.verticals.ace.storage.loader import (
    staging_dataset_dir,
    activate_staging_dataset,
    rollback_to_version,
    archive_dataset_dir,
)

router = APIRouter(
    prefix="/admin/datasets",
    tags=["datasets-admin"],
)

audit = AuditLog(audit_db_path())


@router.post("/activate/{dataset_id}")
def activate_dataset(
    dataset_id: str,
    admin: AdminIdentity = Depends(require_admin),
):
    ds = staging_dataset_dir(dataset_id)

    res = validate_dataset_bundle(ds)
    if not res.ok:
        audit.append(
            event_id=f"dataset_activate_failed:{dataset_id}:{uuid.uuid4().hex}",
            event_type="DATASET_ACTIVATE_FAILED",
            actor=admin,
            meta={
                "dataset_id": dataset_id,
                "errors": [e.__dict__ for e in res.errors],
                "warnings": [w.__dict__ for w in res.warnings],
            },
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
        audit.append(
            event_id=f"dataset_activate_error:{dataset_id}:{uuid.uuid4().hex}",
            event_type="DATASET_ACTIVATE_ERROR",
            actor=admin,
            meta={"dataset_id": dataset_id, "message": act.message},
        )
        raise HTTPException(status_code=500, detail={"message": act.message})

    audit.append_deduped(
        event_id=f"dataset_activated:{dataset_id}:{act.new_dataset_id}",
        event_type="DATASET_ACTIVATED",
        actor=admin,
        meta={
            "dataset_id": dataset_id,
            "activated_dataset_id": act.new_dataset_id,
            "previous_archived_id": act.previous_archived_id,
        },
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
    admin: AdminIdentity = Depends(require_admin),
):
    ds = archive_dataset_dir(version_id)

    res = validate_dataset_bundle(ds)
    if not res.ok:
        audit.append(
            event_id=f"dataset_rollback_failed:{version_id}:{uuid.uuid4().hex}",
            event_type="DATASET_ROLLBACK_FAILED",
            actor=admin,
            meta={
                "version_id": version_id,
                "errors": [e.__dict__ for e in res.errors],
                "warnings": [w.__dict__ for w in res.warnings],
            },
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
        audit.append(
            event_id=f"dataset_rollback_error:{version_id}:{uuid.uuid4().hex}",
            event_type="DATASET_ROLLBACK_ERROR",
            actor=admin,
            meta={"version_id": version_id, "message": rb.message},
        )
        raise HTTPException(status_code=500, detail={"message": rb.message})

    audit.append_deduped(
        event_id=f"dataset_rolled_back:{version_id}:{rb.new_dataset_id}",
        event_type="DATASET_ROLLED_BACK",
        actor=admin,
        meta={
            "version_id": version_id,
            "active_version_id": rb.new_dataset_id,
            "previous_archived_id": rb.previous_archived_id,
        },
    )

    return {
        "ok": True,
        "activeVersionId": rb.new_dataset_id,
        "previousArchivedId": rb.previous_archived_id,
        "message": rb.message,
    }

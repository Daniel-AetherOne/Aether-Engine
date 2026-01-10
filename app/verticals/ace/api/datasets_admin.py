from fastapi import APIRouter, HTTPException

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


@router.post("/activate/{dataset_id}")
def activate_dataset(dataset_id: str):
    ds = staging_dataset_dir(dataset_id)

    res = validate_dataset_bundle(ds)
    if not res.ok:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validation failed; cannot activate dataset.",
                "errors": [e.__dict__ for e in res.errors],
                "warnings": [w.__dict__ for w in res.warnings],
            },
        )

    act = activate_staging_dataset(dataset_id, uploaded_by="admin")
    if not act.ok:
        raise HTTPException(status_code=500, detail={"message": act.message})

    return {
        "ok": True,
        "activeVersionId": act.new_dataset_id,
        "previousArchivedId": act.previous_archived_id,
        "message": act.message,
    }


@router.post("/rollback/{version_id}")
def rollback_dataset(version_id: str):
    ds = archive_dataset_dir(version_id)

    res = validate_dataset_bundle(ds)
    if not res.ok:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validation failed; cannot rollback to this version.",
                "errors": [e.__dict__ for e in res.errors],
                "warnings": [w.__dict__ for w in res.warnings],
            },
        )

    rb = rollback_to_version(version_id, uploaded_by="admin")
    if not rb.ok:
        raise HTTPException(status_code=500, detail={"message": rb.message})

    return {
        "ok": True,
        "activeVersionId": rb.new_dataset_id,
        "previousArchivedId": rb.previous_archived_id,
        "message": rb.message,
    }

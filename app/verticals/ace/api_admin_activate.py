from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, HTTPException

from app.verticals.ace.data_validators import validate_dataset_bundle
from app.verticals.ace.storage.loader import (
    staging_dataset_dir,
    activate_staging_dataset,
)

router = APIRouter(prefix="/admin/datasets", tags=["datasets-admin"])


@router.post("/activate/{dataset_id}")
def activate(dataset_id: str):
    ds = staging_dataset_dir(dataset_id)
    res = validate_dataset_bundle(ds)
    if not res.ok:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validation failed; cannot activate.",
                "errors": [e.__dict__ for e in res.errors],
                "warnings": [w.__dict__ for w in res.warnings],
            },
        )

    act = activate_staging_dataset(dataset_id)
    if not act.ok:
        raise HTTPException(status_code=500, detail={"message": act.message})

    return {
        "ok": True,
        "activatedDatasetId": act.new_dataset_id,
        "previousArchivedId": act.previous_archived_id,
        "message": act.message,
    }

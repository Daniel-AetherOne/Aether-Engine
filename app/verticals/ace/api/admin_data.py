from __future__ import annotations

import shutil
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.verticals.ace.api.dependencies.admin_auth import require_admin
from app.verticals.ace.domain.auth import AdminIdentity
from app.verticals.ace.audit.logger import audit_logger, AuditWrite

from app.verticals.ace.data_validators import validate_dataset_bundle
from app.verticals.ace.storage.loader import (
    staging_dataset_dir,
    activate_staging_dataset,
    rollback_to_version,
    archive_root,
    active_dir,
    ensure_base_dirs,
)
from app.verticals.ace.storage.manifest import read_manifest

router = APIRouter(prefix="/admin/data", tags=["admin-data"])
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)

DATASET_TYPES = [
    ("articles", "articles.csv", {".csv"}),
    ("tiers", "tiers.csv", {".csv"}),
    ("supplier_factors", "supplier_factors.csv", {".csv"}),
    ("transport", "transport.csv", {".csv"}),
    ("customers", "customers.xlsx", {".xlsx"}),
]


def _now_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"v{ts}_{uuid.uuid4().hex[:8]}"


def _list_archive_versions(limit: int = 50) -> list[str]:
    if not archive_root().exists():
        return []
    dirs = [p.name for p in archive_root().iterdir() if p.is_dir()]
    dirs.sort(reverse=True)
    return dirs[:limit]


def _safe_ext(filename: str) -> str:
    return Path(filename).suffix.lower()


@router.get("", response_class=HTMLResponse)
def admin_page(
    request: Request,
    dataset_id: Optional[str] = None,
    admin: AdminIdentity = Depends(require_admin),
):
    ensure_base_dirs()

    if dataset_id is None:
        dataset_id = _now_id()

    staging_path = staging_dataset_dir(dataset_id)
    staging_path.mkdir(parents=True, exist_ok=True)

    uploaded = []
    for _, fname, _exts in DATASET_TYPES:
        if (staging_path / fname).exists():
            uploaded.append(fname)

    active_manifest = None
    try:
        active_manifest = read_manifest(active_dir())
    except Exception:
        active_manifest = None

    archive_versions = _list_archive_versions()

    # Optional: log viewing (dedup per dataset+admin)
    audit_logger.log_deduped(
        AuditWrite(
            action_type="ADMIN_DATA_VIEWED",
            actor=admin,
            target_type="DATASET_STAGING",
            target_id=dataset_id,
            meta={"dataset_id": dataset_id},
            audit_id=f"admin_data_viewed:{dataset_id}:{admin.username}",
        )
    )

    return templates.TemplateResponse(
        "admin_data.html",
        {
            "request": request,
            "dataset_id": dataset_id,
            "dataset_types": DATASET_TYPES,
            "uploaded_files": uploaded,
            "active_manifest": active_manifest,
            "archive_versions": archive_versions,
            "result": None,
        },
    )


@router.post("/upload")
async def upload_file(
    dataset_id: str = Form(...),
    dataset_type: str = Form(...),
    file: UploadFile = File(...),
    admin: AdminIdentity = Depends(require_admin),
):
    ensure_base_dirs()

    mapping = {t: (fname, exts) for (t, fname, exts) in DATASET_TYPES}
    if dataset_type not in mapping:
        audit_logger.log(
            AuditWrite(
                action_type="DATASET_UPLOAD_FAILED",
                actor=admin,
                target_type="DATASET_STAGING",
                target_id=dataset_id,
                meta={
                    "dataset_id": dataset_id,
                    "dataset_type": dataset_type,
                    "reason": "unknown_dataset_type",
                },
                audit_id=f"dataset_upload_failed:{dataset_id}:{uuid.uuid4().hex}",
            )
        )
        raise HTTPException(status_code=400, detail="Unknown dataset_type")

    canonical_name, allowed_exts = mapping[dataset_type]
    ext = _safe_ext(file.filename or "")
    if ext not in allowed_exts:
        audit_logger.log(
            AuditWrite(
                action_type="DATASET_UPLOAD_FAILED",
                actor=admin,
                target_type="DATASET_STAGING",
                target_id=dataset_id,
                meta={
                    "dataset_id": dataset_id,
                    "dataset_type": dataset_type,
                    "filename": file.filename,
                    "reason": "invalid_extension",
                    "ext": ext,
                    "allowed": sorted(allowed_exts),
                },
                audit_id=f"dataset_upload_failed:{dataset_id}:{uuid.uuid4().hex}",
            )
        )
        raise HTTPException(
            status_code=400,
            detail=f"Invalid extension {ext}. Allowed: {sorted(allowed_exts)}",
        )

    ds_dir = staging_dataset_dir(dataset_id)
    ds_dir.mkdir(parents=True, exist_ok=True)
    dest = ds_dir / canonical_name

    audit_logger.log(
        AuditWrite(
            action_type="DATASET_UPLOAD_STARTED",
            actor=admin,
            target_type="DATASET_STAGING",
            target_id=dataset_id,
            meta={
                "dataset_id": dataset_id,
                "dataset_type": dataset_type,
                "filename": file.filename,
                "stored_as": dest.name,
            },
            audit_id=f"dataset_upload_started:{dataset_id}:{dataset_type}:{uuid.uuid4().hex}",
        )
    )

    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
    finally:
        try:
            await file.close()
        except Exception:
            pass

    audit_logger.log_deduped(
        AuditWrite(
            action_type="DATASET_UPLOAD_COMPLETED",
            actor=admin,
            target_type="DATASET_STAGING",
            target_id=dataset_id,
            meta={
                "dataset_id": dataset_id,
                "dataset_type": dataset_type,
                "stored_as": dest.name,
            },
            audit_id=f"dataset_upload_completed:{dataset_id}:{dataset_type}:{dest.name}",
        )
    )

    return RedirectResponse(url=f"/admin/data?dataset_id={dataset_id}", status_code=303)


@router.post("/validate")
def validate(
    dataset_id: str = Form(...),
    admin: AdminIdentity = Depends(require_admin),
):
    ds_dir = staging_dataset_dir(dataset_id)
    res = validate_dataset_bundle(ds_dir)

    audit_logger.log(
        AuditWrite(
            action_type="DATASET_VALIDATED",
            actor=admin,
            target_type="DATASET_STAGING",
            target_id=dataset_id,
            meta={
                "dataset_id": dataset_id,
                "ok": res.ok,
                "errors": [asdict(e) for e in res.errors],
                "warnings": [asdict(w) for w in res.warnings],
            },
            audit_id=f"dataset_validated:{dataset_id}:{uuid.uuid4().hex}",
        )
    )

    return JSONResponse(
        {
            "ok": res.ok,
            "errors": [asdict(e) for e in res.errors],
            "warnings": [asdict(w) for w in res.warnings],
            "datasetId": dataset_id,
        }
    )


@router.post("/activate")
def activate(
    dataset_id: str = Form(...),
    admin: AdminIdentity = Depends(require_admin),
):
    ds_dir = staging_dataset_dir(dataset_id)
    res = validate_dataset_bundle(ds_dir)
    if not res.ok:
        audit_logger.log(
            AuditWrite(
                action_type="DATASET_ACTIVATE_FAILED",
                actor=admin,
                target_type="DATASET_STAGING",
                target_id=dataset_id,
                meta={
                    "dataset_id": dataset_id,
                    "errors": [asdict(e) for e in res.errors],
                    "warnings": [asdict(w) for w in res.warnings],
                },
                audit_id=f"dataset_activate_failed:{dataset_id}:{uuid.uuid4().hex}",
            )
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validation failed; cannot activate.",
                "errors": [asdict(e) for e in res.errors],
                "warnings": [asdict(w) for w in res.warnings],
            },
        )

    act = activate_staging_dataset(dataset_id, uploaded_by=admin.username)
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

    return RedirectResponse(url="/admin/data", status_code=303)


@router.post("/rollback")
def rollback(
    version_id: str = Form(...),
    admin: AdminIdentity = Depends(require_admin),
):
    ds_dir = archive_root() / version_id
    res = validate_dataset_bundle(ds_dir)
    if not res.ok:
        audit_logger.log(
            AuditWrite(
                action_type="DATASET_ROLLBACK_FAILED",
                actor=admin,
                target_type="DATASET_ARCHIVE",
                target_id=version_id,
                meta={
                    "version_id": version_id,
                    "errors": [asdict(e) for e in res.errors],
                    "warnings": [asdict(w) for w in res.warnings],
                },
                audit_id=f"dataset_rollback_failed:{version_id}:{uuid.uuid4().hex}",
            )
        )
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validation failed; cannot rollback.",
                "errors": [asdict(e) for e in res.errors],
                "warnings": [asdict(w) for w in res.warnings],
            },
        )

    rb = rollback_to_version(version_id, uploaded_by=admin.username)
    if not rb.ok:
        audit_logger.log(
            AuditWrite(
                action_type="DATASET_ROLLBACK_ERROR",
                actor=admin,
                target_type="DATASET_ARCHIVE",
                target_id=version_id,
                meta={"version_id": version_id, "message": rb.message},
                audit_id=f"dataset_rollback_error:{version_id}:{uuid.uuid4().hex}",
            )
        )
        raise HTTPException(status_code=500, detail={"message": rb.message})

    audit_logger.log_deduped(
        AuditWrite(
            action_type="DATASET_ROLLED_BACK",
            actor=admin,
            target_type="DATASET",
            target_id=version_id,
            old_value={"active_before": rb.previous_archived_id},
            new_value={"active_after": rb.new_dataset_id},
            meta={
                "version_id": version_id,
                "active_version_id": rb.new_dataset_id,
                "previous_archived_id": rb.previous_archived_id,
            },
            audit_id=f"dataset_rolled_back:{version_id}:{rb.new_dataset_id}",
        )
    )

    return RedirectResponse(url="/admin/data", status_code=303)


@router.post("/reset_staging")
def reset_staging(
    dataset_id: str = Form(...),
    admin: AdminIdentity = Depends(require_admin),
):
    ds_dir = staging_dataset_dir(dataset_id)
    existed = ds_dir.exists()
    if existed:
        shutil.rmtree(ds_dir)

    audit_logger.log(
        AuditWrite(
            action_type="STAGING_RESET",
            actor=admin,
            target_type="DATASET_STAGING",
            target_id=dataset_id,
            meta={"dataset_id": dataset_id, "existed": existed},
            audit_id=f"staging_reset:{dataset_id}:{uuid.uuid4().hex}",
        )
    )

    return RedirectResponse(url="/admin/data", status_code=303)

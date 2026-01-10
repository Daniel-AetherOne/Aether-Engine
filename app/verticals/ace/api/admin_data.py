from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

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

security = HTTPBasic()

ADMIN_USER = os.getenv("ACE_ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ACE_ADMIN_PASS", "admin")


def require_basic_auth(creds: HTTPBasicCredentials = Depends(security)) -> None:
    if creds.username != ADMIN_USER or creds.password != ADMIN_PASS:
        raise HTTPException(status_code=401, detail="Unauthorized")


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
    # newest first (lexicographic works because your archive ids start with timestamp)
    dirs.sort(reverse=True)
    return dirs[:limit]


def _safe_ext(filename: str) -> str:
    return Path(filename).suffix.lower()


@router.get("", response_class=HTMLResponse, dependencies=[Depends(require_basic_auth)])
def admin_page(request: Request, dataset_id: Optional[str] = None):
    """
    Basic admin UI:
    - create/continue a staging dataset_id (query param)
    - upload files into it
    - validate, activate
    - show history for rollback
    """
    ensure_base_dirs()

    if dataset_id is None:
        dataset_id = _now_id()

    staging_path = staging_dataset_dir(dataset_id)
    staging_path.mkdir(parents=True, exist_ok=True)

    uploaded = []
    for _, fname, _exts in DATASET_TYPES:
        if (staging_path / fname).exists():
            uploaded.append(fname)

    # active manifest (if exists)
    active_manifest = None
    try:
        active_manifest = read_manifest(active_dir())
    except Exception:
        active_manifest = None

    archive_versions = _list_archive_versions()

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


@router.post("/upload", dependencies=[Depends(require_basic_auth)])
async def upload_file(
    dataset_id: str = Form(...),
    dataset_type: str = Form(...),
    file: UploadFile = File(...),
):
    ensure_base_dirs()

    # map type -> canonical filename + allowed ext
    mapping = {t: (fname, exts) for (t, fname, exts) in DATASET_TYPES}
    if dataset_type not in mapping:
        raise HTTPException(status_code=400, detail="Unknown dataset_type")

    canonical_name, allowed_exts = mapping[dataset_type]
    ext = _safe_ext(file.filename or "")
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid extension {ext}. Allowed: {sorted(allowed_exts)}",
        )

    ds_dir = staging_dataset_dir(dataset_id)
    ds_dir.mkdir(parents=True, exist_ok=True)

    dest = ds_dir / canonical_name

    # Replace-only policy: always overwrite canonical file
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

    # back to UI
    return RedirectResponse(url=f"/admin/data?dataset_id={dataset_id}", status_code=303)


@router.post("/validate", dependencies=[Depends(require_basic_auth)])
def validate(dataset_id: str = Form(...)):
    ds_dir = staging_dataset_dir(dataset_id)
    res = validate_dataset_bundle(ds_dir)

    # Return JSON if you want API-only usage
    return JSONResponse(
        {
            "ok": res.ok,
            "errors": [asdict(e) for e in res.errors],
            "warnings": [asdict(w) for w in res.warnings],
            "datasetId": dataset_id,
        }
    )


@router.post("/activate", dependencies=[Depends(require_basic_auth)])
def activate(dataset_id: str = Form(...)):
    ds_dir = staging_dataset_dir(dataset_id)
    res = validate_dataset_bundle(ds_dir)
    if not res.ok:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validation failed; cannot activate.",
                "errors": [asdict(e) for e in res.errors],
                "warnings": [asdict(w) for w in res.warnings],
            },
        )

    act = activate_staging_dataset(dataset_id, uploaded_by="admin")
    if not act.ok:
        raise HTTPException(status_code=500, detail={"message": act.message})

    # after activation, go back to UI with fresh dataset_id
    return RedirectResponse(url="/admin/data", status_code=303)


@router.post("/rollback", dependencies=[Depends(require_basic_auth)])
def rollback(version_id: str = Form(...)):
    # Validate bundle BEFORE rollback (safety)
    ds_dir = archive_root() / version_id
    res = validate_dataset_bundle(ds_dir)
    if not res.ok:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Validation failed; cannot rollback.",
                "errors": [asdict(e) for e in res.errors],
                "warnings": [asdict(w) for w in res.warnings],
            },
        )

    rb = rollback_to_version(version_id, uploaded_by="admin")
    if not rb.ok:
        raise HTTPException(status_code=500, detail={"message": rb.message})

    return RedirectResponse(url="/admin/data", status_code=303)


@router.post("/reset_staging", dependencies=[Depends(require_basic_auth)])
def reset_staging(dataset_id: str = Form(...)):
    """
    Handy button: delete current staging dataset directory.
    """
    ds_dir = staging_dataset_dir(dataset_id)
    if ds_dir.exists():
        shutil.rmtree(ds_dir)
    return RedirectResponse(url="/admin/data", status_code=303)

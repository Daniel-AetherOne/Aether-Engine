# app/tasks/vision_task.py
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models import Lead, LeadFile
from app.services.storage import get_storage

logger = logging.getLogger(__name__)


def _tmp_dir_for_lead(lead_id: int) -> Path:
    """
    Cloud Run only guarantees /tmp as writable.
    We keep a per-lead folder for repeatability during one run.
    """
    base = Path(os.getenv("UPLOAD_DIR", "/tmp/uploads"))
    d = base / "vision" / str(lead_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _collect_image_paths(files: List[LeadFile], lead: Lead) -> List[str]:
    """
    Prefer LeadFile.local_path; otherwise download from storage using LeadFile.s3_key.

    IMPORTANT:
    - LeadFile.s3_key is stored tenant-less in DB.
    - Storage backend is responsible for tenant-prefixing (S3) if needed.
    """
    paths: List[str] = []

    # 1) local_path if present and exists
    for f in files:
        lp = getattr(f, "local_path", None)
        if lp:
            try:
                p = Path(str(lp))
                if p.exists() and p.is_file() and p.stat().st_size > 0:
                    paths.append(str(p))
            except Exception:
                # ignore broken local paths
                pass

    if paths:
        return paths

    # 2) fallback: download from Storage via s3_key
    storage = get_storage()
    tenant_id = str(getattr(lead, "tenant_id", "") or "").strip()
    lead_id = int(getattr(lead, "id"))

    # Keep stable per-lead tmp dir (useful for debugging)
    tmp_dir = _tmp_dir_for_lead(lead_id)

    for f in files:
        key = getattr(f, "s3_key", None)
        if not key:
            continue

        key_str = str(key).strip().lstrip("/")
        if not key_str:
            continue

        try:
            # Preferred: use storage helper (handles tenant prefixing for S3)
            local_path = storage.download_to_temp_path(tenant_id=tenant_id, key=key_str)

            # Optionally copy into our lead tmp dir (so file name is nice/predictable)
            # but only if download path isn't already within tmp_dir
            try:
                p = Path(local_path)
                if p.exists() and p.is_file() and p.stat().st_size > 0:
                    # If file already in our lead tmp folder, keep it
                    if tmp_dir in p.parents:
                        paths.append(str(p))
                    else:
                        # copy to stable location
                        dst = tmp_dir / (Path(key_str).name or p.name)
                        if not dst.exists() or dst.stat().st_size == 0:
                            dst.write_bytes(p.read_bytes())
                        paths.append(str(dst))
                else:
                    raise RuntimeError("download_returned_empty_file")
            except Exception as e:
                logger.warning(
                    f"Downloaded but could not validate/copy file for key={key_str} lead_id={lead_id}: {e}"
                )

        except Exception as e:
            logger.warning(
                f"Failed to download key={key_str} tenant_id={tenant_id} lead_id={lead_id}: {e}"
            )

    return paths


def _paintly_enabled() -> bool:
    """
    Prefer settings if present, else fall back to env var.
    Accepts: "1"/"true"/"yes" as enabled.
    """
    v = getattr(settings, "ENABLE_PAINTLY", None)
    if v is None:
        v = os.getenv("ENABLE_PAINTLY", "0")
    return str(v).strip().lower() in {"1", "true", "yes", "y"}


def run_vision_for_lead(db: Session, lead_id: int) -> Dict[str, Any]:
    """
    Runs vision for a lead:
    - loads Lead + LeadFile
    - collects local image paths (local_path OR downloads via storage using s3_key)
    - runs predict_images(local_paths)
    - aggregates for paintly if enabled
    - stores on lead.vision_json or lead.vision_output
    """
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise ValueError("Lead not found")

    files: List[LeadFile] = db.query(LeadFile).filter(LeadFile.lead_id == lead_id).all()
    if not files:
        raise ValueError("No files found for this lead (LeadFile records missing).")

    image_paths = _collect_image_paths(files, lead)
    if not image_paths:
        raise ValueError(
            "No usable image paths. LeadFile.local_path is empty and downloads via LeadFile.s3_key failed."
        )

    # Run image-level predictions (will heuristic-fallback if torch not installed)
    from app.tasks.vision import predict_images

    image_predictions = predict_images(image_paths)

    # Decide aggregation strategy (Paintly)
    if _paintly_enabled():
        # For now: keep it simple and store raw predictions.
        # (Later you can add a paintly-specific aggregator here.)
        vision_output: Dict[str, Any] = {
            "mode": "image_predictions_only",
            "reason": "paintly_default",
            "image_predictions": image_predictions,
        }
    else:
        vision_output = {
            "mode": "image_predictions_only",
            "reason": "paintly_disabled",
            "image_predictions": image_predictions,
        }

    # Optional validation (only if we ever add surfaces aggregation)
    surfaces = (
        vision_output.get("surfaces") if isinstance(vision_output, dict) else None
    )
    if surfaces == []:
        logger.warning(
            f"Vision output has empty surfaces for lead_id={lead_id}. "
            f"images={len(image_paths)} preds={len(image_predictions)}"
        )

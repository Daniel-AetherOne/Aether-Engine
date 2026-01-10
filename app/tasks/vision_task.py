# app/tasks/vision_task.py
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

import boto3
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models import Lead, LeadFile

logger = logging.getLogger(__name__)


def _get_s3_client():
    return boto3.client("s3", region_name=settings.AWS_REGION)


def _tmp_dir_for_lead(lead_id: int) -> Path:
    """
    Cloud Run only guarantees /tmp as writable.
    """
    base = Path(os.getenv("UPLOAD_DIR", "/tmp/uploads"))
    d = base / "vision" / str(lead_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _download_s3_key_to_local(s3_key: str, lead_id: int) -> str:
    """
    Download one S3 object to a local temp file and return the local path.
    """
    tmp_dir = _tmp_dir_for_lead(lead_id)

    filename = Path(s3_key).name or f"{s3_key.replace('/', '_')}.jpg"
    local_path = tmp_dir / filename

    if local_path.exists() and local_path.stat().st_size > 0:
        return str(local_path)

    s3 = _get_s3_client()
    s3.download_file(settings.S3_BUCKET, s3_key, str(local_path))
    return str(local_path)


def _collect_image_paths(files: List[LeadFile], lead_id: int) -> List[str]:
    """
    Prefer local_path; otherwise download from S3 using s3_key.
    """
    paths: List[str] = []

    # 1) local_path if present
    for f in files:
        lp = getattr(f, "local_path", None)
        if lp:
            paths.append(str(lp))

    if paths:
        return paths

    # 2) fallback: download from S3 (s3_key)
    for f in files:
        key = getattr(f, "s3_key", None)
        if not key:
            continue
        try:
            paths.append(_download_s3_key_to_local(str(key), lead_id))
        except Exception as e:
            logger.warning(
                f"Failed to download S3 key={key} for lead_id={lead_id}: {e}"
            )

    return paths


def _painters_us_enabled() -> bool:
    """
    Prefer settings if present, else fall back to env var.
    Accepts: "1"/"true"/"yes" as enabled.
    """
    v = getattr(settings, "ENABLE_PAINTERS_US", None)
    if v is None:
        v = os.getenv("ENABLE_PAINTERS_US", "0")
    return str(v).strip().lower() in {"1", "true", "yes", "y"}


def run_vision_for_lead(db: Session, lead_id: int) -> Dict[str, Any]:
    """
    Runs vision for a lead:
    - loads Lead + LeadFile
    - collects local image paths (local_path OR downloads from S3 via s3_key)
    - runs predict_images(local_paths)  (safe: falls back if torch missing)
    - if painters_us enabled: aggregates to surface-level output
      else: store raw image_predictions
    - stores on lead.vision_json (string) or lead.vision_output (dict)
    """

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise ValueError("Lead not found")

    files: List[LeadFile] = db.query(LeadFile).filter(LeadFile.lead_id == lead_id).all()
    if not files:
        raise ValueError("No files found for this lead (LeadFile records missing).")

    image_paths = _collect_image_paths(files, lead_id)
    if not image_paths:
        raise ValueError(
            "No usable image paths. LeadFile.local_path is empty and S3 downloads via LeadFile.s3_key failed."
        )

    # Run image-level predictions (will heuristic-fallback if torch not installed)
    from app.tasks.vision import predict_images

    image_predictions = predict_images(image_paths)

    # Decide aggregation strategy
    if _painters_us_enabled():
        try:
            from app.verticals.painters_us.vision_aggregate_us import (
                aggregate_images_to_surfaces,
            )

            vision_output: Dict[str, Any] = aggregate_images_to_surfaces(
                image_predictions
            )
        except Exception as e:
            logger.exception(
                f"PaintersUS aggregation failed for lead_id={lead_id}: {e}"
            )
            vision_output = {
                "mode": "image_predictions_only",
                "reason": "aggregation_failed",
                "error": str(e),
                "image_predictions": image_predictions,
            }
    else:
        vision_output = {
            "mode": "image_predictions_only",
            "reason": "painters_us_disabled",
            "image_predictions": image_predictions,
        }

    # Optional validation
    surfaces = (
        vision_output.get("surfaces") if isinstance(vision_output, dict) else None
    )
    if _painters_us_enabled() and not surfaces:
        logger.warning(
            f"Vision aggregation produced empty surfaces for lead_id={lead_id}. "
            f"images={len(image_paths)} preds={len(image_predictions)}"
        )

    # Store on lead
    payload = json.dumps(vision_output)

    if hasattr(lead, "vision_json"):
        lead.vision_json = payload
    elif hasattr(lead, "vision_output"):
        lead.vision_output = vision_output
    else:
        lead.notes = lead.notes or ""
        lead.notes += "\n\nVISION_JSON=" + payload

    db.commit()
    return vision_output

# app/tasks/vision_task.py
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models import Lead, LeadFile
from app.tasks.vision import predict_images
from app.verticals.painters_us.vision_aggregate_us import aggregate_images_to_surfaces

logger = logging.getLogger(__name__)


def _get_s3_client():
    return boto3.client("s3", region_name=settings.AWS_REGION)


def _tmp_dir_for_lead(lead_id: int) -> Path:
    d = Path(".tmp") / "vision" / str(lead_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _download_s3_key_to_local(s3_key: str, lead_id: int) -> str:
    """
    Download one S3 object to a local temp file and return the local path.
    """
    tmp_dir = _tmp_dir_for_lead(lead_id)

    # Keep original filename if possible
    filename = Path(s3_key).name or f"{s3_key.replace('/', '_')}.jpg"
    local_path = tmp_dir / filename

    # Skip download if file already exists
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


def run_vision_for_lead(db: Session, lead_id: int) -> Dict[str, Any]:
    """
    Runs vision for a lead:
    - loads Lead + LeadFile
    - collects local image paths (local_path OR downloads from S3 via s3_key)
    - runs predict_images(local_paths)
    - aggregates to surface-level vision_output for painters_us
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

    # Run image-level predictions
    image_predictions = predict_images(image_paths)

    # US painters surface-level aggregation (MVP)
    vision_output = aggregate_images_to_surfaces(image_predictions)

    # Validate output
    surfaces = (
        vision_output.get("surfaces") if isinstance(vision_output, dict) else None
    )
    if not surfaces:
        logger.warning(
            f"Vision aggregation produced empty surfaces for lead_id={lead_id}. "
            f"images={len(image_paths)} preds={len(image_predictions)}"
        )

    # Store on lead for later publish/render
    if hasattr(lead, "vision_json"):
        lead.vision_json = json.dumps(vision_output)
    elif hasattr(lead, "vision_output"):
        lead.vision_output = vision_output
    else:
        # last resort: store in notes (not recommended)
        lead.notes = (lead.notes or "") + "\n\nVISION_JSON=" + json.dumps(vision_output)

        # ALWAYS also store a backup in notes (for MVP debugging / compatibility)
        lead.notes = lead.notes or ""
        lead.notes += "\n\nVISION_JSON=" + json.dumps(vision_output)

    db.commit()
    return vision_output

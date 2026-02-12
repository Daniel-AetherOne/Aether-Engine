# app/services/photo_quality/inference.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Optional

import numpy as np
from PIL import Image

from app.services.storage import Storage


@dataclass
class PhotoQualityResult:
    quality: str  # "good" | "bad"
    score_bad: float
    reasons: List[str]


def _maybe_strip_tenant(object_key: str, tenant_id: str) -> str:
    """
    Our DB stores object_key as tenant-prefixed:
      "<tenant_id>/uploads/....jpg"

    Storage helpers typically want:
      tenant_id + key_without_tenant

    So: if object_key starts with "<tenant_id>/", strip it.
    """
    if not object_key:
        return object_key
    prefix = f"{tenant_id}/"
    if tenant_id and object_key.startswith(prefix):
        return object_key[len(prefix) :]
    return object_key


def _laplacian_variance(gray: np.ndarray) -> float:
    g = gray.astype(np.float32)

    up = np.roll(g, -1, axis=0)
    down = np.roll(g, 1, axis=0)
    left = np.roll(g, -1, axis=1)
    right = np.roll(g, 1, axis=1)

    lap = (4.0 * g) - up - down - left - right
    return float(lap.var())


def _analyze_image(local_path: str) -> Tuple[float, List[str]]:
    reasons: List[str] = []

    try:
        img = Image.open(local_path).convert("RGB")
    except Exception:
        return 0.0, ["photo_unreadable"]

    w, h = img.size
    if w < 640 or h < 480:
        reasons.append("resolution_too_low")

    # downscale for speed
    img_small = img.copy()
    img_small.thumbnail((1024, 1024))

    arr = np.asarray(img_small, dtype=np.uint8)
    gray = (
        0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2]
    ).astype(np.float32)

    sharp = _laplacian_variance(gray)

    if sharp < 30:
        reasons.append("too_blurry")

    return sharp, reasons


def predict_photo_quality(
    image_refs: List[str],
    storage: Storage,
    tenant_id: str,
) -> PhotoQualityResult:
    """
    image_refs are UploadRecord.object_key values (often tenant-prefixed).
    storage must support download_to_temp_path(tenant_id, key) (your S3Storage/LocalStorage does).
    """
    if not image_refs:
        return PhotoQualityResult("bad", 0.99, ["no_photos"])

    sharps: List[float] = []
    reasons_all: List[str] = []

    for obj in image_refs[:5]:
        key_wo_tenant = _maybe_strip_tenant(obj, tenant_id)
        if not key_wo_tenant:
            reasons_all.append("bad_object_key")
            continue

        try:
            tmp_path = storage.download_to_temp_path(tenant_id, key_wo_tenant)
        except Exception:
            reasons_all.append("download_failed")
            continue

        sharp, rs = _analyze_image(tmp_path)
        sharps.append(sharp)
        reasons_all.extend(rs)

        # cleanup (best effort)
        try:
            import os

            os.remove(tmp_path)
        except Exception:
            pass

    if not sharps:
        # nothing analyzable
        reasons = list(dict.fromkeys(reasons_all)) or ["no_readable_photos"]
        return PhotoQualityResult("bad", 0.99, reasons)

    best = max(sharps)

    # Map best sharpness to bad probability in [0.05..0.95]
    # best >= 80 => ~0.05 bad
    # best <= 20 => ~0.95 bad
    score = float(np.clip((80.0 - best) / 60.0, 0.0, 1.0))
    score_bad = 0.05 + 0.90 * score

    # Decision: if at least one photo is sharp enough, we call it good
    quality = "good" if best >= 80 else "bad"

    reasons = list(dict.fromkeys(reasons_all))
    if quality == "good":
        reasons = [r for r in reasons if r != "too_blurry"]

    return PhotoQualityResult(quality, score_bad, reasons)

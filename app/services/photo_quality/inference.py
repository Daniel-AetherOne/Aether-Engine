from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
from PIL import Image


@dataclass
class PhotoQualityResult:
    quality: str  # "good" | "bad"
    score_bad: float
    reasons: List[str]


# -------------------------
# Heuristics thresholds (MVP)
# -------------------------
MIN_LONG_EDGE_PX = 900  # too small => bad
DARK_MEAN_LUMA = 45.0  # too dark => bad (0-255)
BRIGHT_MEAN_LUMA = 245.0  # too bright => bad
LOW_CONTRAST_STD = 18.0  # low contrast => bad
BLUR_LAPLACIAN_VAR = 60.0  # lower => blurrier => bad

# Aggregate decision threshold
THRESHOLD_BAD = 0.60


def _image_to_gray_np(img: Image.Image, max_side: int = 1024) -> np.ndarray:
    """Convert to grayscale numpy array, downscale for speed."""
    img = img.convert("RGB")
    w, h = img.size
    scale = min(1.0, float(max_side) / float(max(w, h)))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)))
    gray = img.convert("L")
    return np.asarray(gray, dtype=np.float32)


def _laplacian_var(gray: np.ndarray) -> float:
    """
    Approx Laplacian variance without OpenCV.
    Uses a simple Laplacian kernel convolution.
    """
    # 2D convolution with Laplacian kernel:
    # [ 0,  1, 0]
    # [ 1, -4, 1]
    # [ 0,  1, 0]
    g = gray
    # pad edges
    gp = np.pad(g, 1, mode="edge")
    lap = (
        gp[0:-2, 1:-1]
        + gp[2:, 1:-1]
        + gp[1:-1, 0:-2]
        + gp[1:-1, 2:]
        - 4.0 * gp[1:-1, 1:-1]
    )
    return float(np.var(lap))


def _score_from_reasons(reasons: List[str]) -> float:
    """
    Simple weighted mapping: reasons -> bad score.
    You can tune these later.
    """
    if not reasons:
        return 0.0

    weights = {
        "low_resolution": 0.55,
        "too_dark": 0.75,
        "too_bright": 0.75,
        "low_contrast": 0.60,
        "blurry": 0.75,
        "unreadable": 0.90,
    }
    # Combine weights into a score (1 - product(1-w))
    p = 1.0
    for r in reasons:
        w = float(weights.get(r, 0.50))
        p *= 1.0 - max(0.0, min(1.0, w))
    return float(1.0 - p)


def _analyze_one_image(path: str) -> Tuple[float, List[str]]:
    """
    Returns (score_bad, reasons) for one image.
    """
    reasons: List[str] = []
    try:
        with Image.open(path) as img:
            w, h = img.size
            long_edge = max(w, h)
            if long_edge < MIN_LONG_EDGE_PX:
                reasons.append("low_resolution")

            gray = _image_to_gray_np(img)

        mean = float(np.mean(gray))
        std = float(np.std(gray))
        if mean <= DARK_MEAN_LUMA:
            reasons.append("too_dark")
        if mean >= BRIGHT_MEAN_LUMA:
            reasons.append("too_bright")
        if std <= LOW_CONTRAST_STD:
            reasons.append("low_contrast")

        lv = _laplacian_var(gray)
        if lv <= BLUR_LAPLACIAN_VAR:
            reasons.append("blurry")

        score_bad = _score_from_reasons(reasons)
        return score_bad, reasons

    except Exception:
        # cannot open/parse
        reasons = ["unreadable"]
        return _score_from_reasons(reasons), reasons


def predict_photo_quality(
    image_refs: list[str],
    storage,
    tenant_id: str,
) -> PhotoQualityResult:
    """
    image_refs: storage object_keys (S3 keys or local keys)
    storage: app.services.storage.get_storage() instance
    tenant_id: scope for storage reads
    """
    if not image_refs:
        return PhotoQualityResult(
            quality="bad",
            score_bad=1.0,
            reasons=["no_photos"],
        )

    worst_score = 0.0
    merged_reasons: List[str] = []

    # Analyze each image; if any is bad, we bias toward NEEDS_REVIEW
    for key in image_refs:
        tmp_path = storage.download_to_temp_path(tenant_id, key)
        try:
            score_bad, reasons = _analyze_one_image(tmp_path)

            if score_bad > worst_score:
                worst_score = score_bad

            # keep unique reasons across images
            for r in reasons:
                if r not in merged_reasons:
                    merged_reasons.append(r)
        finally:
            # best-effort cleanup temp files (S3Storage creates temp files)
            try:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    quality = "bad" if worst_score >= THRESHOLD_BAD else "good"
    return PhotoQualityResult(
        quality=quality,
        score_bad=float(worst_score),
        reasons=merged_reasons,
    )

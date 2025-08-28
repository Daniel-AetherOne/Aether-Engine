# app/services/predictor.py
import os
from pathlib import Path
from typing import List, Dict, Tuple
import numpy as np
from PIL import Image

# cv2 pas importeren wanneer nodig
def _cv2():
    import cv2  # headless variant zit in requirements
    return cv2


class SimplePredictor:
    """Simple heuristic-based predictor for substrate and issues without ML"""

    def __init__(self):
        self.substrate_types = ["gipsplaat", "beton", "bestaand"]
        self.issue_types = ["scheuren", "vocht"]
        # hard cap om enorme foto’s te begrenzen (RAM/CPU sparen)
        self.max_side = int(os.getenv("PREDICT_MAX_SIDE", "1600"))

    def predict(self, lead_id: str, image_paths: List[str], m2: float) -> Dict:
        if not image_paths:
            return self._default_prediction()

        first_image_path = image_paths[0]
        try:
            # Laad 1x, converteer naar RGB en downscale
            with Image.open(first_image_path) as img_pil:
                img_pil = img_pil.convert("RGB")
                img_pil = self._downscale(img_pil, self.max_side)
                img = np.array(img_pil)

            substrate_pred, substrate_conf = self._analyze_substrate(img)
            issues_pred, issues_conf = self._analyze_issues(img)

            return {
                "substrate": substrate_pred,
                "issues": issues_pred,
                "confidences": {
                    "substrate": substrate_conf,
                    **issues_conf,
                },
            }
        except Exception as e:
            print(f"Error analyzing image {first_image_path}: {e}")
            return self._default_prediction()

    # ---------- helpers ----------

    def _downscale(self, img_pil: Image.Image, max_side: int) -> Image.Image:
        w, h = img_pil.size
        scale = min(1.0, max_side / max(w, h))
        if scale < 1.0:
            new_size = (int(w * scale), int(h * scale))
            img_pil = img_pil.resize(new_size, resample=Image.BILINEAR)
        return img_pil

    def _to_gray(self, img_rgb: np.ndarray) -> np.ndarray:
        if img_rgb.ndim == 3:
            cv2 = _cv2()
            gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_rgb
        return gray

    # ---------- analyses ----------

    def _analyze_substrate(self, img_rgb: np.ndarray) -> Tuple[str, float]:
        try:
            cv2 = _cv2()
            gray = self._to_gray(img_rgb)

            contrast = self._calculate_contrast(gray)
            noise_level = self._calculate_noise(gray, cv2)
            edge_density = self._calculate_edge_density(gray, cv2)
            texture_variance = self._calculate_texture_variance(gray, cv2)

            if contrast > 0.6 and edge_density > 0.3:
                return "beton", min(0.8, 0.5 + contrast * 0.3)
            elif noise_level > 0.4 and texture_variance > 0.5:
                return "bestaand", min(0.75, 0.4 + noise_level * 0.35)
            elif contrast < 0.4 and edge_density < 0.2:
                return "gipsplaat", min(0.7, 0.5 + (1 - contrast) * 0.2)
            else:
                return "bestaand", 0.65

        except Exception as e:
            print(f"Error in substrate analysis: {e}")
            return "bestaand", 0.5

    def _analyze_issues(self, img_rgb: np.ndarray) -> Tuple[List[str], Dict[str, float]]:
        try:
            cv2 = _cv2()
            gray = self._to_gray(img_rgb)

            detected_issues: List[str] = []
            issue_confidences: Dict[str, float] = {}

            crack_confidence = self._detect_cracks(gray, cv2)
            if crack_confidence > 0.4:
                detected_issues.append("scheuren")
                issue_confidences["scheuren"] = crack_confidence

            moisture_confidence = self._detect_moisture(img_rgb, cv2)
            if moisture_confidence > 0.3:
                detected_issues.append("vocht")
                issue_confidences["vocht"] = moisture_confidence

            issue_confidences.setdefault("scheuren", 0.2)
            issue_confidences.setdefault("vocht", 0.15)

            return detected_issues, issue_confidences

        except Exception as e:
            print(f"Error in issue analysis: {e}")
            return [], {"scheuren": 0.2, "vocht": 0.15}

    # ---------- metrics ----------

    def _calculate_contrast(self, gray: np.ndarray) -> float:
        try:
            contrast = float(np.std(gray)) / 255.0
            return min(1.0, contrast)
        except Exception:
            return 0.5

    def _calculate_noise(self, gray: np.ndarray, cv2) -> float:
        try:
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            noise = np.mean(np.abs(gray.astype(np.float32) - blurred.astype(np.float32))) / 255.0
            return min(1.0, float(noise))
        except Exception:
            return 0.5

    def _calculate_edge_density(self, gray: np.ndarray, cv2) -> float:
        try:
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.count_nonzero(edges) / (edges.shape[0] * edges.shape[1])
            return min(1.0, edge_density * 10.0)
        except Exception:
            return 0.3

    def _calculate_texture_variance(self, gray: np.ndarray, cv2) -> float:
        try:
            kernel = np.ones((5, 5), dtype=np.float32) / 25.0
            mean = cv2.filter2D(gray.astype(np.float32), -1, kernel)
            variance = cv2.filter2D((gray.astype(np.float32) - mean) ** 2, -1, kernel)
            texture_var = float(np.mean(variance)) / (255.0 ** 2)
            return min(1.0, texture_var * 100.0)
        except Exception:
            return 0.4

    def _detect_cracks(self, gray: np.ndarray, cv2) -> float:
        try:
            kernel = np.ones((3, 3), np.uint8)
            edges = cv2.Canny(gray, 30, 100)
            dilated = cv2.dilate(edges, kernel, iterations=1)
            crack_score = np.count_nonzero(dilated) / (dilated.shape[0] * dilated.shape[1])
            return min(1.0, crack_score * 20.0)
        except Exception:
            return 0.3

    def _detect_moisture(self, rgb: np.ndarray, cv2) -> float:
        try:
            if rgb.ndim != 3:
                return 0.2
            hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
            lower = np.array([0, 0, 0], dtype=np.uint8)
            upper = np.array([180, 100, 100], dtype=np.uint8)
            mask = cv2.inRange(hsv, lower, upper)
            ratio = np.count_nonzero(mask) / (mask.shape[0] * mask.shape[1])
            return min(1.0, ratio * 5.0)
        except Exception:
            return 0.2

    def _default_prediction(self) -> Dict:
        return {
            "substrate": "bestaand",
            "issues": [],
            "confidences": {"substrate": 0.5, "scheuren": 0.2, "vocht": 0.15},
        }

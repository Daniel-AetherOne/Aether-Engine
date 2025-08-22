import os
from pathlib import Path
from typing import List, Dict, Tuple
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import cv2

class SimplePredictor:
    """Simple heuristic-based predictor for substrate and issues without ML"""
    
    def __init__(self):
        self.substrate_types = ["gipsplaat", "beton", "bestaand"]
        self.issue_types = ["scheuren", "vocht"]
        
    def predict(self, lead_id: str, image_paths: List[str], m2: float) -> Dict:
        """
        Predict substrate type and issues based on image analysis
        
        Args:
            lead_id: Unique identifier for the lead
            image_paths: List of paths to uploaded images
            m2: Square meters of the area
            
        Returns:
            Dictionary with predictions and confidences
        """
        if not image_paths:
            return self._default_prediction()
        
        # Analyze first image for substrate and issues
        first_image_path = image_paths[0]
        
        try:
            # Load and analyze image
            substrate_pred, substrate_conf = self._analyze_substrate(first_image_path)
            issues_pred, issues_conf = self._analyze_issues(first_image_path)
            
            return {
                "substrate": substrate_pred,
                "issues": issues_pred,
                "confidences": {
                    "substrate": substrate_conf,
                    **issues_conf
                }
            }
        except Exception as e:
            print(f"Error analyzing image {first_image_path}: {e}")
            return self._default_prediction()
    
    def _analyze_substrate(self, image_path: str) -> Tuple[str, float]:
        """Analyze image to determine substrate type"""
        try:
            # Load image
            img = Image.open(image_path)
            img_array = np.array(img)
            
            # Convert to grayscale if needed
            if len(img_array.shape) == 3:
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            else:
                gray = img_array
            
            # Calculate various features
            contrast = self._calculate_contrast(gray)
            noise_level = self._calculate_noise(gray)
            edge_density = self._calculate_edge_density(gray)
            texture_variance = self._calculate_texture_variance(gray)
            
            # Decision logic based on heuristics
            if contrast > 0.6 and edge_density > 0.3:
                # High contrast and edges suggest concrete
                return "beton", min(0.8, 0.5 + contrast * 0.3)
            elif noise_level > 0.4 and texture_variance > 0.5:
                # High noise and texture variance suggest existing surface
                return "bestaand", min(0.75, 0.4 + noise_level * 0.35)
            elif contrast < 0.4 and edge_density < 0.2:
                # Low contrast and edges suggest drywall
                return "gipsplaat", min(0.7, 0.5 + (1 - contrast) * 0.2)
            else:
                # Default to existing surface
                return "bestaand", 0.65
                
        except Exception as e:
            print(f"Error in substrate analysis: {e}")
            return "bestaand", 0.5
    
    def _analyze_issues(self, image_path: str) -> Tuple[List[str], Dict[str, float]]:
        """Analyze image to detect issues"""
        try:
            # Load image
            img = Image.open(image_path)
            img_array = np.array(img)
            
            # Convert to grayscale if needed
            if len(img_array.shape) == 3:
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            else:
                gray = img_array
            
            detected_issues = []
            issue_confidences = {}
            
            # Detect cracks using edge detection
            crack_confidence = self._detect_cracks(gray)
            if crack_confidence > 0.4:
                detected_issues.append("scheuren")
                issue_confidences["scheuren"] = crack_confidence
            
            # Detect moisture using color analysis
            moisture_confidence = self._detect_moisture(img_array)
            if moisture_confidence > 0.3:
                detected_issues.append("vocht")
                issue_confidences["vocht"] = moisture_confidence
            
            # Set default confidences for undetected issues
            if "scheuren" not in issue_confidences:
                issue_confidences["scheuren"] = 0.2
            if "vocht" not in issue_confidences:
                issue_confidences["vocht"] = 0.15
            
            return detected_issues, issue_confidences
            
        except Exception as e:
            print(f"Error in issue analysis: {e}")
            return [], {"scheuren": 0.2, "vocht": 0.15}
    
    def _calculate_contrast(self, gray_image: np.ndarray) -> float:
        """Calculate image contrast"""
        try:
            # Use standard deviation as contrast measure
            contrast = np.std(gray_image) / 255.0
            return min(1.0, contrast)
        except:
            return 0.5
    
    def _calculate_noise(self, gray_image: np.ndarray) -> float:
        """Calculate image noise level"""
        try:
            # Apply Gaussian blur and compare with original
            blurred = cv2.GaussianBlur(gray_image, (5, 5), 0)
            noise = np.mean(np.abs(gray_image.astype(float) - blurred.astype(float))) / 255.0
            return min(1.0, noise)
        except:
            return 0.5
    
    def _calculate_edge_density(self, gray_image: np.ndarray) -> float:
        """Calculate edge density using Canny edge detection"""
        try:
            # Apply Canny edge detection
            edges = cv2.Canny(gray_image, 50, 150)
            edge_density = np.sum(edges > 0) / (edges.shape[0] * edges.shape[1])
            return min(1.0, edge_density * 10)  # Scale up for better range
        except:
            return 0.3
    
    def _calculate_texture_variance(self, gray_image: np.ndarray) -> float:
        """Calculate texture variance"""
        try:
            # Calculate local variance using a small kernel
            kernel = np.ones((5, 5)) / 25
            mean = cv2.filter2D(gray_image.astype(float), -1, kernel)
            variance = cv2.filter2D((gray_image.astype(float) - mean) ** 2, -1, kernel)
            texture_var = np.mean(variance) / (255.0 ** 2)
            return min(1.0, texture_var * 100)  # Scale up for better range
        except:
            return 0.4
    
    def _detect_cracks(self, gray_image: np.ndarray) -> float:
        """Detect cracks using edge analysis"""
        try:
            # Apply morphological operations to enhance cracks
            kernel = np.ones((3, 3), np.uint8)
            edges = cv2.Canny(gray_image, 30, 100)
            
            # Dilate edges to connect crack lines
            dilated = cv2.dilate(edges, kernel, iterations=1)
            
            # Calculate crack-like features
            crack_score = np.sum(dilated > 0) / (dilated.shape[0] * dilated.shape[1])
            
            # Normalize and return confidence
            confidence = min(1.0, crack_score * 20)  # Scale up for better range
            return confidence
        except:
            return 0.3
    
    def _detect_moisture(self, color_image: np.ndarray) -> float:
        """Detect moisture using color analysis"""
        try:
            if len(color_image.shape) != 3:
                return 0.2
            
            # Convert to HSV for better color analysis
            hsv = cv2.cvtColor(color_image, cv2.COLOR_RGB2HSV)
            
            # Look for dark, saturated areas (potential moisture)
            # Lower saturation and value thresholds for moisture detection
            lower_moisture = np.array([0, 0, 0])
            upper_moisture = np.array([180, 100, 100])
            
            moisture_mask = cv2.inRange(hsv, lower_moisture, upper_moisture)
            moisture_ratio = np.sum(moisture_mask > 0) / (moisture_mask.shape[0] * moisture_mask.shape[1])
            
            # Calculate confidence based on moisture ratio
            confidence = min(1.0, moisture_ratio * 5)  # Scale up for better range
            return confidence
        except:
            return 0.2
    
    def _default_prediction(self) -> Dict:
        """Return default prediction when analysis fails"""
        return {
            "substrate": "bestaand",
            "issues": [],
            "confidences": {
                "substrate": 0.5,
                "scheuren": 0.2,
                "vocht": 0.15
            }
        }

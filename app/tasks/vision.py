import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import transforms
from PIL import Image
import timm
import numpy as np
from typing import List, Dict, Tuple, Optional
import json
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class LevelAIModel(nn.Module):
    """LevelAI model met backbone en twee heads voor substrate en issues classificatie"""
    
    def __init__(self, num_substrates: int = 3, num_issues: int = 2, backbone_name: str = "efficientnet_b0"):
        super().__init__()
        
        # Backbone (EfficientNet)
        self.backbone = timm.create_model(backbone_name, pretrained=True, num_classes=0)
        backbone_features = self.backbone.num_features
        
        # Head voor substrate classificatie (softmax)
        self.head_substrate = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Dropout(0.3),
            nn.Linear(backbone_features, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, num_substrates)
        )
        
        # Head voor issues classificatie (sigmoid)
        self.head_issues = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Dropout(0.3),
            nn.Linear(backbone_features, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, num_issues)
        )
        
        # Klassen definities
        self.substrate_classes = ["gipsplaat", "beton", "bestaand"]
        self.issue_classes = ["scheuren", "vocht"]
        
    def forward(self, x):
        # Backbone features
        features = self.backbone.forward_features(x)
        
        # Substrate classificatie
        substrate_logits = self.head_substrate(features)
        
        # Issues classificatie
        issues_logits = self.head_issues(features)
        
        return substrate_logits, issues_logits

class VisionPredictor:
    """Vision predictor voor LevelAI met model loading en inference"""
    
    def __init__(self, model_path: Optional[str] = None):
        self.model = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.transform = self._get_transforms()
        
        if model_path and os.path.exists(model_path):
            self.load_model(model_path)
        else:
            logger.warning(f"Model path {model_path} niet gevonden, gebruik fallback heuristiek")
    
    def _get_transforms(self):
        """Transform pipeline voor inference"""
        return transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], 
                               std=[0.229, 0.224, 0.225])
        ])
    
    def load_model(self, model_path: str):
        """Laad het getrainde model"""
        try:
            self.model = LevelAIModel()
            checkpoint = torch.load(model_path, map_location=self.device)
            self.model.load_state_dict(checkpoint)
            self.model.to(self.device)
            self.model.eval()
            logger.info(f"Model geladen van {model_path}")
        except Exception as e:
            logger.error(f"Fout bij laden model: {e}")
            self.model = None
    
    def _heuristic_fallback(self, image_path: str) -> Dict:
        """Fallback heuristiek als model niet beschikbaar is"""
        # Simpele heuristiek gebaseerd op bestandsnaam en extensie
        filename = Path(image_path).stem.lower()
        
        # Substrate heuristiek
        if "gips" in filename or "gipsplaat" in filename:
            substrate = "gipsplaat"
            substrate_conf = 0.8
        elif "beton" in filename:
            substrate = "beton"
            substrate_conf = 0.8
        else:
            substrate = "bestaand"
            substrate_conf = 0.6
        
        # Issues heuristiek
        issues = []
        issue_confs = []
        
        if "scheur" in filename or "crack" in filename:
            issues.append("scheuren")
            issue_confs.append(0.7)
        
        if "vocht" in filename or "water" in filename or "moisture" in filename:
            issues.append("vocht")
            issue_confs.append(0.7)
        
        # Als geen issues gevonden, voeg "geen" toe
        if not issues:
            issues.append("geen")
            issue_confs.append(0.5)
        
        return {
            "substrate": substrate,
            "substrate_confidence": substrate_conf,
            "issues": issues,
            "issue_confidences": issue_confs,
            "method": "heuristic_fallback"
        }
    
    def predict(self, image_paths: List[str]) -> List[Dict]:
        """Voorspel substrate en issues voor een lijst van afbeeldingen"""
        results = []
        
        for image_path in image_paths:
            try:
                if self.model is None:
                    # Gebruik fallback heuristiek
                    result = self._heuristic_fallback(image_path)
                else:
                    # Gebruik PyTorch model
                    result = self._predict_with_model(image_path)
                
                result["image_path"] = image_path
                results.append(result)
                
            except Exception as e:
                logger.error(f"Fout bij voorspellen van {image_path}: {e}")
                # Fallback bij fout
                result = self._heuristic_fallback(image_path)
                result["image_path"] = image_path
                result["error"] = str(e)
                results.append(result)
        
        return results
    
    def _predict_with_model(self, image_path: str) -> Dict:
        """Voorspel met PyTorch model"""
        # Laad en transformeer afbeelding
        image = Image.open(image_path).convert('RGB')
        image_tensor = self.transform(image).unsqueeze(0).to(self.device)
        
        # Inference
        with torch.no_grad():
            substrate_logits, issues_logits = self.model(image_tensor)
            
            # Substrate (softmax)
            substrate_probs = F.softmax(substrate_logits, dim=1)
            substrate_pred = torch.argmax(substrate_probs, dim=1).item()
            substrate_conf = substrate_probs[0, substrate_pred].item()
            
            # Issues (sigmoid)
            issues_probs = torch.sigmoid(issues_logits)
            issues_mask = issues_probs > 0.5
            issues_indices = torch.where(issues_mask)[1].tolist()
            
            issues = [self.model.issue_classes[i] for i in issues_indices]
            issue_confs = [issues_probs[0, i].item() for i in issues_indices]
            
            # Als geen issues gedetecteerd, voeg "geen" toe
            if not issues:
                issues = ["geen"]
                issue_confs = [0.5]
        
        return {
            "substrate": self.model.substrate_classes[substrate_pred],
            "substrate_confidence": substrate_conf,
            "issues": issues,
            "issue_confidences": issue_confs,
            "method": "pytorch_model"
        }

# Global predictor instance
_vision_predictor = None

def get_vision_predictor(model_path: Optional[str] = None) -> VisionPredictor:
    """Get of maak vision predictor instance"""
    global _vision_predictor
    
    if _vision_predictor is None:
        if model_path is None:
            # Zoek naar model in standaard locaties
            possible_paths = [
                "models/levelai_vision_model.pth",
                "app/models/levelai_vision_model.pth",
                "data/models/levelai_vision_model.pth"
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    model_path = path
                    break
        
        _vision_predictor = VisionPredictor(model_path)
    
    return _vision_predictor

def predict_images(image_paths: List[str], model_path: Optional[str] = None) -> List[Dict]:
    """Hoofdfunctie voor image prediction"""
    predictor = get_vision_predictor(model_path)
    return predictor.predict(image_paths)

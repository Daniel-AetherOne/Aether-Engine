from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from pathlib import Path
from typing import List, Optional
import os
import time

from app.models.predict import PredictRequest, PredictResponse
from app.services.predictor import SimplePredictor
from app.tasks.vision import predict_images, get_vision_predictor
from app.rate_limiting import prediction_rate_limit, vision_rate_limit
from app.logging_config import get_logger
from app.metrics import record_vision_metrics, record_lead_metrics
from app.dependencies import resolve_tenant

router = APIRouter()
predictor = SimplePredictor()
logger = get_logger(__name__)

@router.post("/", response_model=PredictResponse)
@prediction_rate_limit()
async def predict_substrate_and_issues(
    request: PredictRequest,
    tenant_id: str = Depends(resolve_tenant)
):
    """
    Predict substrate type and detect issues based on uploaded images
    
    This endpoint uses simple heuristics to analyze images and provide predictions
    without requiring a trained ML model.
    """
    try:
        # Validate that images exist
        valid_image_paths = []
        for image_path in request.image_paths:
            if Path(image_path).exists():
                valid_image_paths.append(image_path)
            else:
                print(f"Warning: Image path not found: {image_path}")
        
        if not valid_image_paths:
            raise HTTPException(
                status_code=400, 
                detail="No valid image paths provided. Please ensure images exist and are accessible."
            )
        
        # Make prediction using the simple predictor
        prediction = predictor.predict(
            lead_id=request.lead_id,
            image_paths=valid_image_paths,
            m2=request.m2
        )
        
        return PredictResponse(**prediction)
        
    except Exception as e:
        print(f"Error in prediction endpoint: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error during prediction: {str(e)}"
        )

@router.post("/vision", response_model=dict)
@vision_rate_limit()
async def predict_vision(
    files: List[UploadFile] = File(...),
    model_path: Optional[str] = None,
    tenant_id: str = Depends(resolve_tenant)
):
    """
    Vision prediction endpoint voor LevelAI
    
    Upload afbeeldingen en krijg substrate en issues voorspellingen.
    Gebruikt PyTorch model als beschikbaar, anders fallback heuristiek.
    """
    try:
        # Sla geüploade bestanden op
        uploaded_paths = []
        upload_dir = Path("data/uploads/vision")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        for file in files:
            if not file.content_type.startswith('image/'):
                continue
                
            # Genereer unieke bestandsnaam
            file_extension = Path(file.filename).suffix
            unique_filename = f"vision_{len(uploaded_paths):04d}{file_extension}"
            file_path = upload_dir / unique_filename
            
            # Sla bestand op
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            
            uploaded_paths.append(str(file_path))
        
        if not uploaded_paths:
            raise HTTPException(
                status_code=400,
                detail="Geen geldige afbeeldingen geüpload"
            )
        
        # Maak voorspellingen
        predictions = predict_images(uploaded_paths, model_path)
        
        return {
            "status": "success",
            "predictions": predictions,
            "model_used": "pytorch" if any(p.get("method") == "pytorch_model" for p in predictions) else "heuristic",
            "total_images": len(predictions)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fout bij vision prediction: {str(e)}"
        )

@router.get("/vision/status")
async def vision_status():
    """Check status van vision model"""
    try:
        predictor = get_vision_predictor()
        status = {
            "model_loaded": predictor.model is not None,
            "device": str(predictor.device),
            "fallback_available": True
        }
        
        if predictor.model:
            status["model_info"] = {
                "substrate_classes": predictor.model.substrate_classes,
                "issue_classes": predictor.model.issue_classes
            }
        
        return status
        
    except Exception as e:
        return {
            "model_loaded": False,
            "error": str(e),
            "fallback_available": True
        }

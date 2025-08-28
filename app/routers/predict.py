# app/routers/predict.py
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from app.models.predict import PredictRequest, PredictResponse
from app.services.predictor import SimplePredictor
from app.rate_limiting import prediction_rate_limit, vision_rate_limit
from app.logging_config import get_logger
from app.metrics import record_vision_metrics, record_lead_metrics
from app.dependencies import resolve_tenant

router = APIRouter(prefix="/predict", tags=["predict"])
logger = get_logger(__name__)
predictor = SimplePredictor()


# -------------------------------------------------------------------------
# 1) Heuristiek endpoint: gebruikt alleen SimplePredictor
# -------------------------------------------------------------------------
@router.post("/", response_model=PredictResponse)
@prediction_rate_limit()
async def predict_substrate_and_issues(
    request: PredictRequest,
    tenant_id: str = Depends(resolve_tenant)
):
    """
    Heuristiek-voorspelling zonder zware ML libs.
    Verwacht image_paths (paden op schijf) en m2.
    """
    try:
        if not request.image_paths:
            raise HTTPException(status_code=400, detail="image_paths mag niet leeg zijn.")

        valid_paths: List[str] = []
        for p in request.image_paths:
            if Path(p).exists():
                valid_paths.append(p)
            else:
                logger.warning(f"Image pad niet gevonden: {p}")

        if not valid_paths:
            raise HTTPException(status_code=400, detail="Geen geldige image_paths gevonden.")

        result = predictor.predict(
            lead_id=request.lead_id,
            image_paths=valid_paths,
            m2=request.m2,
        )

        # Optioneel: metrics
        try:
            record_lead_metrics(
                tenant_id=tenant_id,
                lead_id=request.lead_id,
                substrate=result.get("substrate", "unknown"),
            )
        except Exception as m:
            logger.debug(f"Metrics (lead) overslaan: {m}")

        return PredictResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Fout in predict endpoint: {e}")
        raise HTTPException(status_code=500, detail="Interne serverfout tijdens predict.")


# -------------------------------------------------------------------------
# 2) "Vision" upload endpoint (zonder torch): gebruikt óók SimplePredictor
#    Slaat uploads op en geeft per afbeelding een heuristiek-voorspelling.
# -------------------------------------------------------------------------
@router.post("/vision", response_model=dict)
@vision_rate_limit()
async def predict_vision(
    files: List[UploadFile] = File(...),
    model_path: Optional[str] = None,  # aanwezig voor backward compat; wordt niet gebruikt
    tenant_id: str = Depends(resolve_tenant),
):
    """
    Vision prediction zonder PyTorch: pure heuristiek.
    Upload afbeeldingen; we slaan ze tijdelijk op en runnen SimplePredictor per afbeelding.
    """
    try:
        if not files:
            raise HTTPException(status_code=400, detail="Geen bestanden geüpload.")

        upload_dir = Path("data/uploads/vision")
        upload_dir.mkdir(parents=True, exist_ok=True)

        saved_paths: List[str] = []
        for idx, f in enumerate(files):
            if not f.content_type or not f.content_type.startswith("image/"):
                logger.warning(f"Bestand overgeslagen (geen image/*): {f.filename}")
                continue

            suffix = Path(f.filename or "image").suffix or ".jpg"
            fname = f"vision_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{idx:03d}{suffix}"
            dest = upload_dir / fname

            content = await f.read()
            dest.write_bytes(content)
            saved_paths.append(str(dest))

        if not saved_paths:
            raise HTTPException(status_code=400, detail="Geen geldige afbeeldingen geüpload.")

        # Run heuristiek per afbeelding
        results = []
        for p in saved_paths:
            pred = predictor.predict(
                lead_id=f"vision-{tenant_id}",
                image_paths=[p],
                m2=0.0,
            )
            results.append({
                "image_path": p,
                "prediction": pred,
                "method": "heuristic"
            })

        # Optioneel: metrics
        try:
            record_vision_metrics(
                tenant_id=tenant_id,
                total_images=len(saved_paths),
                model_used="heuristic"
            )
        except Exception as m:
            logger.debug(f"Metrics (vision) overslaan: {m}")

        return {
            "status": "success",
            "predictions": results,
            "model_used": "heuristic",
            "total_images": len(results)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Fout bij vision prediction: {e}")
        raise HTTPException(status_code=500, detail="Interne serverfout tijdens vision prediction.")


# -------------------------------------------------------------------------
# 3) Vision status: altijd fallback/heuristiek beschikbaar
# -------------------------------------------------------------------------
@router.get("/vision/status")
async def vision_status():
    """
    Simpele status: geen zwaar model geladen; heuristiek is wel beschikbaar.
    """
    return {
        "model_loaded": False,
        "device": "cpu",
        "fallback_available": True,
        "model_info": {
            "type": "heuristic_only"
        }
    }

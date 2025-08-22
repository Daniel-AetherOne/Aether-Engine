from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional
from app.celery_app import get_job_status
from app.dependencies import resolve_tenant
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

class JobStatusResponse(BaseModel):
    """Response model voor job status"""
    job_id: str
    status: str
    step: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    updated_at: Optional[str] = None
    public_url: Optional[str] = None

@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status_endpoint(
    job_id: str,
    tenant_id: str = Depends(resolve_tenant)
):
    """
    Haal job status op
    
    Returns:
        Job status inclusief huidige stap, resultaat of foutmelding
    """
    try:
        logger.info(f"[TENANT:{tenant_id}] Getting status for job: {job_id}")
        
        # Haal job status op
        job_info = get_job_status(job_id)
        
        if job_info["status"] == "not_found":
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Bereid response voor
        response = JobStatusResponse(
            job_id=job_id,
            status=job_info["status"],
            step=job_info.get("result", {}).get("step") if job_info.get("result") else None,
            result=job_info.get("result"),
            error=job_info.get("error"),
            updated_at=job_info.get("updated_at")
        )
        
        # Voeg public_url toe als de job klaar is en er een quote result is
        if (job_info["status"] == "completed" and 
            job_info.get("result") and 
            job_info["result"].get("step") == "generate_pdf" and
            job_info["result"].get("quote_result")):
            
            response.public_url = job_info["result"]["quote_result"].get("public_url")
        
        logger.info(f"[TENANT:{tenant_id}] Job {job_id} status: {response.status}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[TENANT:{tenant_id}] Error getting job status for {job_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/")
async def list_jobs(tenant_id: str = Depends(resolve_tenant)):
    """
    Lijst alle jobs op voor de huidige tenant
    
    Note: Dit is een basis implementatie. In productie zou je waarschijnlijk
    tenant-specifieke job filtering willen implementeren.
    """
    try:
        logger.info(f"[TENANT:{tenant_id}] Listing jobs")
        
        # Voor nu returnen we een basis response
        # In productie zou je hier tenant-specifieke jobs kunnen filteren
        return {
            "message": "Job listing endpoint - implement tenant-specific filtering as needed",
            "tenant_id": tenant_id
        }
        
    except Exception as e:
        logger.error(f"[TENANT:{tenant_id}] Error listing jobs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

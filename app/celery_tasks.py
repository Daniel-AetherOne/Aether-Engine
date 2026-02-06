from celery import current_task
from app.celery_app import celery_app, update_job_status, logger
from app.services.predictor import SimplePredictor
from app.services.quote_renderer import QuoteRenderer
from app.services.pricing_engine import PricingEngine
from app.services.hubspot_client import HubSpotClient
from app.services.tenant_service import TenantService
from app.models.tenant_settings import TenantSettings
from app.metrics import record_job_metrics
from app.logging_config import set_context
from typing import Dict, Any, List
import traceback
import time

# Initialiseer services
predictor = SimplePredictor()
quote_renderer = QuoteRenderer()
pricing_engine = PricingEngine()
hubspot_client = HubSpotClient()
tenant_service = TenantService()

@celery_app.task(bind=True, name="vision_predict")
def vision_predict_task(self, job_id: str, lead_id: str, image_paths: List[str], m2: float, tenant_id: str, lead_data: Dict[str, Any] = None):
    """Vision prediction taak"""
    start_time = time.time()
    
    # Set logging context
    set_context(tenant_id=tenant_id, lead_id=lead_id)
    
    try:
        logger.info(f"Starting vision_predict for job {job_id}, lead {lead_id}")
        update_job_status(job_id, "processing", {"step": "vision_predict"})
        
        # Voer predictie uit
        prediction = predictor.predict(
            lead_id=lead_id,
            image_paths=image_paths,
            m2=m2
        )
        
        # Calculate duration and record metrics
        duration = time.time() - start_time
        record_job_metrics("vision_predict", tenant_id, "completed", duration)
        
        logger.info(f"Vision prediction completed for job {job_id}: {prediction}")
        update_job_status(job_id, "completed", {
            "step": "vision_predict",
            "prediction": prediction
        })
        
        # Start volgende stap: compute_price
        if lead_data:
            compute_price_task.delay(
                job_id=job_id,
                m2=m2,
                substrate=prediction.get("substrate", "bestaand"),
                issues=prediction.get("issues", []),
                lead_data=lead_data,
                tenant_id=tenant_id
            )
            logger.info(f"Enqueued compute_price task for job {job_id}")
        
        return prediction
        
    except Exception as e:
        # Calculate duration and record metrics
        duration = time.time() - start_time
        record_job_metrics("vision_predict", tenant_id, "failed", duration)
        
        error_msg = f"Vision prediction failed: {str(e)}"
        logger.error(f"Error in vision_predict for job {job_id}: {error_msg}")
        update_job_status(job_id, "failed", error=error_msg)
        raise

@celery_app.task(bind=True, name="generate_pdf")
def generate_pdf_task(self, job_id: str, lead_data: Dict[str, Any], prediction: Dict[str, Any], 
                     pricing_result: Dict[str, Any], tenant_id: str):
    """PDF generatie taak"""
    try:
        logger.info(f"Starting generate_pdf for job {job_id}")
        update_job_status(job_id, "processing", {"step": "generate_pdf"})
        
        # Haal tenant settings op
        tenant_settings = tenant_service.get_tenant(tenant_id)
        if not tenant_settings:
            raise Exception(f"Tenant {tenant_id} not found")
        
        # Genereer offerte
        quote_result = quote_renderer.render_quote(
            lead=lead_data,
            prediction=prediction,
            pricing=pricing_result,
            tenant_settings=tenant_settings
        )
        
        logger.info(f"PDF generation completed for job {job_id}: {quote_result}")
        update_job_status(job_id, "completed", {
            "step": "generate_pdf",
            "quote_result": quote_result
        })
        
        # Start laatste stap: crm_push
        crm_push_task.delay(
            job_id=job_id,
            lead_data=lead_data,
            quote_result=quote_result,
            pricing_result=pricing_result,
            tenant_id=tenant_id
        )
        logger.info(f"Enqueued crm_push task for job {job_id}")
        
        return quote_result
        
    except Exception as e:
        error_msg = f"PDF generation failed: {str(e)}"
        logger.error(f"Error in generate_pdf for job {job_id}: {error_msg}")
        update_job_status(job_id, "failed", error=error_msg)
        raise

@celery_app.task(bind=True, name="crm_push")
def crm_push_task(self, job_id: str, lead_data: Dict[str, Any], quote_result: Dict[str, Any], 
                 pricing_result: Dict[str, Any], tenant_id: str):
    """CRM push taak"""
    try:
        logger.info(f"Starting crm_push for job {job_id}")
        update_job_status(job_id, "processing", {"step": "crm_push"})
        
        # Haal tenant settings op
        tenant_settings = tenant_service.get_tenant(tenant_id)
        if not tenant_settings or not tenant_settings.hubspot_token:
            logger.info(f"HubSpot not configured for tenant {tenant_id}, skipping CRM push")
            update_job_status(job_id, "completed", {
                "step": "crm_push",
                "message": "HubSpot not configured"
            })
            return {"message": "HubSpot not configured"}
        
        # Configureer HubSpot client
        hubspot_client.set_token(tenant_settings.hubspot_token)
        
        # Bereid quote data voor CRM push
        quote_data_for_crm = {
            "quote_id": quote_result["quote_id"],
            "total": pricing_result["total"],
            "html_url": quote_result["html_url"],
            "pdf_url": quote_result["public_url"],
            "year_month": quote_result["year_month"]
        }
        
        # Push naar HubSpot CRM
        contact_id = hubspot_client.upsert_contact(
            email=lead_data["email"],
            name=lead_data["name"],
            phone=lead_data.get("phone", "")
        )
        
        if contact_id:
            deal_id = hubspot_client.create_deal(
                amount=pricing_result["total"],
                name=f"Offerte {quote_result['quote_id']} - {lead_data['name']}"
            )
            
            if deal_id:
                # Koppel contact aan deal
                hubspot_client.associate_contact_with_deal(contact_id, deal_id)
                
                # Voeg note toe met offerte URL
                hubspot_client.attach_note(deal_id, quote_result["html_url"])
                
                logger.info(f"CRM push completed for job {job_id} - Contact: {contact_id}, Deal: {deal_id}")
                update_job_status(job_id, "completed", {
                    "step": "crm_push",
                    "contact_id": contact_id,
                    "deal_id": deal_id
                })
                return {"contact_id": contact_id, "deal_id": deal_id}
            else:
                raise Exception("Failed to create deal in HubSpot")
        else:
            raise Exception("Failed to create contact in HubSpot")
        
    except Exception as e:
        error_msg = f"CRM push failed: {str(e)}"
        logger.error(f"Error in crm_push for job {job_id}: {error_msg}")
        update_job_status(job_id, "failed", error=error_msg)
        raise

@celery_app.task(bind=True, name="compute_price")
def compute_price_task(self, job_id: str, m2: float, substrate: str, issues: List[str], lead_data: Dict[str, Any] = None, tenant_id: str = None):
    """Prijsberekening taak"""
    try:
        logger.info(f"Starting compute_price for job {job_id}")
        update_job_status(job_id, "processing", {"step": "compute_price"})
        
        # Bereken prijs
        pricing_result = pricing_engine.compute_price(
            m2=m2,
            substrate=substrate,
            issues=issues
        )
        
        logger.info(f"Price computation completed for job {job_id}: {pricing_result}")
        update_job_status(job_id, "completed", {
            "step": "compute_price",
            "pricing_result": pricing_result
        })
        
        # Start volgende stap: generate_pdf
        if lead_data and tenant_id:
            generate_pdf_task.delay(
                job_id=job_id,
                lead_data=lead_data,
                prediction={"substrate": substrate, "issues": issues},
                pricing_result=pricing_result,
                tenant_id=tenant_id
            )
            logger.info(f"Enqueued generate_pdf task for job {job_id}")
        
        return pricing_result
        
    except Exception as e:
        error_msg = f"Price computation failed: {str(e)}"
        logger.error(f"Error in compute_price for job {job_id}: {error_msg}")
        update_job_status(job_id, "failed", error=error_msg)
        raise

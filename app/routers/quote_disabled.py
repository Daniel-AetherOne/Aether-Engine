from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, List
import uuid
from datetime import datetime

from app.services.quote_renderer import QuoteRenderer
from app.services.pricing_engine import PricingEngine
from app.services.predictor import SimplePredictor
from app.services.hubspot_client import HubSpotClient
from app.dependencies import resolve_tenant, get_tenant_settings, get_tenant_storage_path
from app.models.tenant import TenantSettings
from app.celery_app import create_job
from app.celery_tasks import vision_predict_task, compute_price_task, generate_pdf_task, crm_push_task
from app.rate_limiting import quote_create_rate_limit
from app.logging_config import get_logger
from app.metrics import record_quote_metrics

# Configureer logging met context
logger = get_logger(__name__)

router = APIRouter()

# Initialiseer services
quote_renderer = QuoteRenderer()
pricing_engine = PricingEngine()
predictor = SimplePredictor()
hubspot_client = HubSpotClient()

# Nieuwe orchestratie endpoint
class QuoteCreateRequest(BaseModel):
    """Request model voor het creeëren van een complete offerte."""
    lead_id: str = Field(..., description="Unieke identifier voor de lead")
    image_paths: List[str] = Field(..., description="Lijst van paden naar geüploade afbeeldingen")
    m2: float = Field(..., gt=0, description="Vierkante meters van het oppervlak (moet groter zijn dan 0)")
    contactgegevens: Dict[str, str] = Field(..., description="Contactgegevens van de klant")

class QuoteCreateResponse(BaseModel):
    """Response model voor het creeëren van een offerte."""
    success: bool
    status_id: str
    message: str
    tenant_id: str

@router.post("/create", response_model=QuoteCreateResponse)
@quote_create_rate_limit()
async def create_quote(
    request: QuoteCreateRequest,
    tenant_id: str = Depends(resolve_tenant),
    tenant_settings: TenantSettings = Depends(get_tenant_settings)
):
    """
    Orchestratie endpoint voor het creeëren van een complete offerte.
    
    Deze endpoint start de volledige flow als asynchrone taken:
    1. Enqueue vision_predict → compute_price → generate_pdf → crm_push
    2. Retourneer onmiddellijk 201 met status_id
    
    Alle stappen worden afgehandeld door Celery workers.
    """
    try:
        logger.info(f"[TENANT:{tenant_id}] Start quote creatie voor lead_id: {request.lead_id}")
        
        # Valideer input
        if not request.image_paths:
            raise HTTPException(status_code=400, detail="image_paths mag niet leeg zijn")
        
        if request.m2 <= 0:
            raise HTTPException(status_code=400, detail="m2 moet groter zijn dan 0")
        
        # Maak nieuwe job aan
        job_id = create_job()
        logger.info(f"[TENANT:{tenant_id}] Created job {job_id} for lead_id: {request.lead_id}")
        
        # Bereid lead data voor
        lead_data = {
            "name": request.contactgegevens.get("name", "Onbekend"),
            "email": request.contactgegevens.get("email", ""),
            "phone": request.contactgegevens.get("phone", ""),
            "address": request.contactgegevens.get("address", ""),
            "square_meters": request.m2
        }
        
        # Start asynchrone workflow met Celery
        # Stap 1: Vision predict
        vision_task = vision_predict_task.delay(
            job_id=job_id,
            lead_id=request.lead_id,
            image_paths=request.image_paths,
            m2=request.m2,
            tenant_id=tenant_id,
            lead_data=lead_data
        )
        
        # Stap 2: Compute price (wordt getriggerd door vision_predict callback)
        # Stap 3: Generate PDF (wordt getriggerd door compute_price callback)
        # Stap 4: CRM push (wordt getriggerd door generate_pdf callback)
        
        # Voor nu gebruiken we een eenvoudige chain (in productie zou je callbacks gebruiken)
        # Dit is een basis implementatie - in productie zou je Celery chains of callbacks gebruiken
        
        logger.info(f"[TENANT:{tenant_id}] Enqueued vision_predict task for job {job_id}")
        
        return QuoteCreateResponse(
            success=True,
            status_id=job_id,
            message="Quote creatie gestart - gebruik status_id om voortgang te volgen",
            tenant_id=tenant_id
        )
        
    except Exception as e:
        logger.error(f"[TENANT:{tenant_id}] Fout bij quote creatie voor lead_id: {request.lead_id} - {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Fout bij quote creatie: {str(e)}"
        )

class QuoteRenderRequest(BaseModel):
    """Request model voor het renderen van een offerte."""
    lead: Dict[str, Any] = Field(..., description="Klantgegevens")
    prediction: Dict[str, Any] = Field(..., description="Voorspelling resultaten")
    
    class Config:
        schema_extra = {
            "example": {
                "lead": {
                    "name": "Jan Jansen",
                    "email": "jan@example.com",
                    "phone": "+31 6 12345678",
                    "address": "Hoofdstraat 123, 1234 AB Amsterdam",
                    "square_meters": 45.5
                },
                "prediction": {
                    "substrate": "gipsplaat",
                    "issues": ["vocht", "scheuren"],
                    "confidences": {
                        "gipsplaat": 0.95,
                        "vocht": 0.87,
                        "scheuren": 0.92
                    }
                }
            }
        }

class QuoteRenderResponse(BaseModel):
    """Response model voor het renderen van een offerte."""
    success: bool
    quote_id: str
    html_path: str
    pdf_path: str | None = None
    public_url: str
    html_url: str
    year_month: str
    tenant_id: str
    message: str = "Offerte succesvol gegenereerd"

class QuoteInfoResponse(BaseModel):
    """Response model voor offerte informatie."""
    quote_id: str
    year_month: str
    tenant_id: str
    html_path: str | None = None
    pdf_path: str | None = None
    html_url: str
    pdf_url: str | None = None
    exists: bool

@router.post("/render", response_model=QuoteRenderResponse)
async def render_quote(
    request: QuoteRenderRequest,
    tenant_id: str = Depends(resolve_tenant),
    tenant_settings: TenantSettings = Depends(get_tenant_settings)
):
    """
    Genereer een offerte op basis van lead, prediction en pricing data met tenant branding.
    
    Deze endpoint:
    1. Berekent de prijs op basis van substrate en issues
    2. Genereert een professionele HTML offerte met tenant branding
    3. Converteert deze naar PDF
    4. Slaat beide bestanden op in data/offers/{tenant_id}/{yyyy-mm}/{quote_id}/
    5. Retourneert de paden en public URLs
    """
    try:
        logger.info(f"[TENANT:{tenant_id}] Start offerte generatie voor lead: {request.lead.get('name', 'Onbekend')}")
        
        # Valideer lead data
        if not request.lead.get("square_meters") or request.lead["square_meters"] <= 0:
            raise HTTPException(status_code=400, detail="square_meters moet groter zijn dan 0")
        
        # Bereken prijs met pricing engine
        pricing_result = pricing_engine.compute_price(
            m2=request.lead["square_meters"],
            substrate=request.prediction.get("substrate", "bestaand"),
            issues=request.prediction.get("issues", [])
        )
        
        # Voeg base_per_m2 toe voor template
        rules = pricing_engine.rules
        substrate = request.prediction.get("substrate", "bestaand")
        pricing_result["base_per_m2"] = rules["base_per_m2"].get(substrate, 0)
        
        logger.info(f"[TENANT:{tenant_id}] Prijs berekend: €{pricing_result['total']} voor {request.lead['square_meters']}m²")
        
        # Render offerte met tenant branding
        quote_result = quote_renderer.render_quote(
            lead=request.lead,
            prediction=request.prediction,
            pricing=pricing_result,
            tenant_settings=tenant_settings
        )
        
        logger.info(f"[TENANT:{tenant_id}] Offerte gegenereerd met ID: {quote_result['quote_id']}")
        
        # CRM push naar HubSpot (alleen als tenant HubSpot heeft geconfigureerd)
        if tenant_settings.hubspot_token:
            try:
                # Configureer HubSpot client met tenant-specifieke token
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
                    email=request.lead["email"],
                    name=request.lead["name"],
                    phone=request.lead.get("phone", "")
                )
                
                if contact_id:
                    deal_id = hubspot_client.create_deal(
                        amount=pricing_result["total"],
                        name=f"Offerte {quote_result['quote_id']} - {request.lead['name']}"
                    )
                    
                    if deal_id:
                        # Koppel contact aan deal
                        hubspot_client.associate_contact_with_deal(contact_id, deal_id)
                        
                        # Voeg note toe met offerte URL
                        hubspot_client.attach_note(deal_id, quote_result["html_url"])
                        
                        logger.info(f"[TENANT:{tenant_id}] CRM push voltooid - Contact: {contact_id}, Deal: {deal_id}")
                    else:
                        logger.warning(f"[TENANT:{tenant_id}] Deal kon niet worden aangemaakt in HubSpot")
                else:
                    logger.warning(f"[TENANT:{tenant_id}] Contact kon niet worden aangemaakt in HubSpot")
                    
            except Exception as crm_error:
                logger.error(f"[TENANT:{tenant_id}] CRM push fout voor quote {quote_result['quote_id']} - {str(crm_error)}")
                # CRM fout mag quote rendering niet blokkeren
        else:
            logger.info(f"[TENANT:{tenant_id}] HubSpot niet geconfigureerd, CRM push overgeslagen")
        
        return QuoteRenderResponse(
            success=True,
            quote_id=quote_result["quote_id"],
            html_path=quote_result["html_path"],
            pdf_path=quote_result.get("pdf_path"),
            public_url=quote_result["public_url"],
            html_url=quote_result["html_url"],
            year_month=quote_result["year_month"],
            tenant_id=tenant_id,
            message="Offerte succesvol gegenereerd"
        )
        
    except Exception as e:
        logger.error(f"[TENANT:{tenant_id}] Fout bij offerte generatie: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Fout bij offerte generatie: {str(e)}"
        )

@router.get("/info/{quote_id}", response_model=QuoteInfoResponse)
async def get_quote_info(
    quote_id: str, 
    year_month: str = None,
    tenant_id: str = Depends(resolve_tenant)
):
    """
    Haal offerte informatie op voor een specifieke tenant.
    
    Args:
        quote_id: Unieke ID van de offerte
        year_month: Jaar-maand directory (optioneel)
        tenant_id: Tenant identifier (automatisch opgehaald uit header)
    """
    try:
        quote_info = quote_renderer.get_quote_info(quote_id, tenant_id, year_month)
        
        return QuoteInfoResponse(
            quote_id=quote_info["quote_id"],
            year_month=quote_info["year_month"],
            tenant_id=quote_info["tenant_id"],
            html_path=quote_info["html_path"],
            pdf_path=quote_info["pdf_path"],
            html_url=quote_info["html_url"],
            pdf_url=quote_info["pdf_url"],
            exists=quote_info["pdf_path"] is not None
        )
        
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, 
            detail=f"Offerte {quote_id} niet gevonden voor tenant {tenant_id}"
        )
    except Exception as e:
        logger.error(f"[TENANT:{tenant_id}] Fout bij ophalen offerte info: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Fout bij ophalen offerte informatie: {str(e)}"
        )

@router.get("/list")
async def list_quotes(
    year_month: str = None,
    tenant_id: str = Depends(resolve_tenant)
):
    """
    Lijst alle offertes op voor een specifieke tenant (optioneel gefilterd op jaar-maand).
    
    Args:
        year_month: Jaar-maand directory (optioneel, format: YYYY-MM)
        tenant_id: Tenant identifier (automatisch opgehaald uit header)
    """
    try:
        quotes_result = quote_renderer.get_tenant_quotes(tenant_id, year_month)
        
        return {
            "quotes": quotes_result["quotes"],
            "total": quotes_result["total_count"],
            "tenant_id": tenant_id,
            "year_month": year_month
        }
            
    except Exception as e:
        logger.error(f"[TENANT:{tenant_id}] Fout bij ophalen offerte lijst: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Fout bij ophalen offerte lijst: {str(e)}"
        )

@router.delete("/{quote_id}")
async def delete_quote(
    quote_id: str, 
    year_month: str = None,
    tenant_id: str = Depends(resolve_tenant)
):
    """
    Verwijder een offerte voor een specifieke tenant.
    
    Args:
        quote_id: Unieke ID van de offerte
        year_month: Jaar-maand directory (optioneel)
        tenant_id: Tenant identifier (automatisch opgehaald uit header)
    """
    try:
        quote_info = quote_renderer.get_quote_info(quote_id, tenant_id, year_month)
        
        # Verwijder bestanden
        import os
        if quote_info["html_path"] and os.path.exists(quote_info["html_path"]):
            os.remove(quote_info["html_path"])
        
        if quote_info["pdf_path"] and os.path.exists(quote_info["pdf_path"]):
            os.remove(quote_info["pdf_path"])
        
        # Verwijder directory als deze leeg is
        tenant_offers_dir = quote_renderer.offers_dir / tenant_id
        quote_dir = tenant_offers_dir / quote_info["year_month"] / quote_id
        if quote_dir.exists() and not any(quote_dir.iterdir()):
            quote_dir.rmdir()
        
        logger.info(f"[TENANT:{tenant_id}] Offerte {quote_id} succesvol verwijderd")
        
        return {"success": True, "message": f"Offerte {quote_id} succesvol verwijderd", "tenant_id": tenant_id}
        
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, 
            detail=f"Offerte {quote_id} niet gevonden voor tenant {tenant_id}"
        )
    except Exception as e:
        logger.error(f"[TENANT:{tenant_id}] Fout bij verwijderen offerte: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Fout bij verwijderen offerte: {str(e)}"
        )

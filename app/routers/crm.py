from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
import logging

from app.services.hubspot_client import HubSpotClient

# Configureer logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# Initialiseer HubSpot client
hubspot_client = HubSpotClient()

class CRMPushRequest(BaseModel):
    """Request model voor CRM push na quote rendering."""
    lead: Dict[str, Any] = Field(..., description="Klantgegevens")
    quote_data: Dict[str, Any] = Field(..., description="Offerte data inclusief URL's")
    
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
                "quote_data": {
                    "quote_id": "ABC12345",
                    "total": 1250.00,
                    "html_url": "http://localhost:8000/files/2024-01/ABC12345/ABC12345.html",
                    "pdf_url": "http://localhost:8000/files/2024-01/ABC12345/ABC12345.pdf",
                    "year_month": "2024-01"
                }
            }
        }

class CRMPushResponse(BaseModel):
    """Response model voor CRM push."""
    success: bool
    message: str
    hubspot_enabled: bool
    contact_id: Optional[str] = None
    deal_id: Optional[str] = None
    note_attached: Optional[bool] = None

@router.post("/push", response_model=CRMPushResponse)
async def push_to_crm(request: CRMPushRequest):
    """
    Push lead en quote data naar HubSpot CRM.
    
    Deze endpoint wordt aangeroepen na render_quote en:
    1. Maakt een contact aan/update in HubSpot
    2. Maakt een deal aan voor de offerte
    3. Koppelt het contact aan de deal
    4. Voegt een note toe met de offerte URL
    
    Als HUBSPOT_ENABLED=false, wordt alles lokaal verwerkt zonder externe calls.
    """
    try:
        logger.info(f"Start CRM push voor quote: {request.quote_data.get('quote_id', 'onbekend')}")
        
        # Valideer input
        if not request.lead.get("email"):
            raise HTTPException(status_code=400, detail="Email is verplicht voor CRM push")
        
        if not request.lead.get("name"):
            raise HTTPException(status_code=400, detail="Naam is verplicht voor CRM push")
        
        if not request.quote_data.get("total"):
            raise HTTPException(status_code=400, detail="Totaal bedrag is verplicht voor CRM push")
        
        # Stap 1: Contact aanmaken/updaten
        logger.info(f"Stap 1: Contact aanmaken/updaten voor {request.lead['email']}")
        contact_id = hubspot_client.upsert_contact(
            email=request.lead["email"],
            name=request.lead["name"],
            phone=request.lead.get("phone", "")
        )
        
        if not contact_id and hubspot_client.enabled:
            logger.warning("Contact kon niet worden aangemaakt in HubSpot")
            return CRMPushResponse(
                success=False,
                message="Contact kon niet worden aangemaakt in HubSpot",
                hubspot_enabled=True
            )
        
        # Stap 2: Deal aanmaken
        logger.info(f"Stap 2: Deal aanmaken voor bedrag €{request.quote_data['total']}")
        deal_name = f"Offerte {request.quote_data.get('quote_id', 'onbekend')} - {request.lead['name']}"
        
        deal_id = hubspot_client.create_deal(
            amount=float(request.quote_data["total"]),
            name=deal_name
        )
        
        if not deal_id and hubspot_client.enabled:
            logger.warning("Deal kon niet worden aangemaakt in HubSpot")
            return CRMPushResponse(
                success=False,
                message="Deal kon niet worden aangemaakt in HubSpot",
                hubspot_enabled=True,
                contact_id=contact_id
            )
        
        # Stap 3: Contact koppelen aan deal
        if contact_id and deal_id:
            logger.info(f"Stap 3: Contact {contact_id} koppelen aan deal {deal_id}")
            association_success = hubspot_client.associate_contact_with_deal(contact_id, deal_id)
            if not association_success and hubspot_client.enabled:
                logger.warning("Contact kon niet worden gekoppeld aan deal")
        
        # Stap 4: Note toevoegen met offerte URL
        note_attached = False
        if deal_id and request.quote_data.get("html_url"):
            logger.info(f"Stap 4: Note toevoegen aan deal {deal_id}")
            note_attached = hubspot_client.attach_note(
                deal_id=deal_id,
                html_url=request.quote_data["html_url"]
            )
        
        # Genereer response bericht
        if hubspot_client.enabled:
            if contact_id and deal_id:
                message = f"Lead en offerte succesvol gepusht naar HubSpot. Contact: {contact_id}, Deal: {deal_id}"
            else:
                message = "Gedeeltelijke CRM push voltooid"
        else:
            message = "CRM push lokaal verwerkt (HubSpot uitgeschakeld)"
        
        logger.info(f"CRM push voltooid voor quote: {request.quote_data.get('quote_id', 'onbekend')}")
        
        return CRMPushResponse(
            success=True,
            message=message,
            hubspot_enabled=hubspot_client.enabled,
            contact_id=contact_id,
            deal_id=deal_id,
            note_attached=note_attached
        )
        
    except Exception as e:
        logger.error(f"Fout bij CRM push: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Fout bij CRM push: {str(e)}"
        )

@router.get("/status")
async def get_crm_status():
    """Haal CRM status op (HubSpot configuratie)."""
    return {
        "hubspot_enabled": hubspot_client.enabled,
        "pipeline": hubspot_client.pipeline,
        "stage": hubspot_client.stage,
        "has_token": bool(hubspot_client.api_token)
    }

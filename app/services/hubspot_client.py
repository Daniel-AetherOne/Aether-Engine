import os
import logging
from typing import Dict, Any, Optional
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

class HubSpotClient:
    """HubSpot CRM client voor contact, deal en note management."""
    
    def __init__(self):
        """Initialiseer de HubSpot client."""
        self.enabled = os.getenv("HUBSPOT_ENABLED", "false").lower() == "true"
        self.api_token = os.getenv("HUBSPOT_TOKEN")
        self.pipeline = os.getenv("PIPELINE", "default")
        self.stage = os.getenv("STAGE", "appointmentscheduled")
        
        self.base_url = "https://api.hubapi.com"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        } if self.api_token else {}
        
        if self.enabled and not self.api_token:
            logger.warning("HubSpot is enabled but no API token provided")
            self.enabled = False
    
    def _make_request(self, method: str, endpoint: str, data: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """Maak een HTTP request naar de HubSpot API."""
        if not self.enabled:
            logger.debug("HubSpot is disabled, skipping API call")
            return None
        
        try:
            url = f"{self.base_url}{endpoint}"
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                json=data,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                return response.json()
            else:
                logger.error(f"HubSpot API error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error making HubSpot API request: {str(e)}")
            return None
    
    def upsert_contact(self, email: str, name: str, phone: str = "") -> Optional[str]:
        """
        Maak een nieuw contact aan of update bestaand contact in HubSpot.
        
        Args:
            email: Email adres van het contact
            name: Naam van het contact
            phone: Telefoonnummer (optioneel)
            
        Returns:
            Contact ID als string, of None bij fout
        """
        if not self.enabled:
            logger.debug("HubSpot is disabled, skipping contact creation")
            return None
        
        # Eerst zoeken naar bestaand contact
        search_data = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "email",
                            "operator": "EQ",
                            "value": email
                        }
                    ]
                }
            ]
        }
        
        search_response = self._make_request("POST", "/crm/v3/objects/contacts/search", search_data)
        
        if search_response and search_response.get("results"):
            # Bestaand contact gevonden, update
            contact_id = search_response["results"][0]["id"]
            update_data = {
                "properties": {
                    "firstname": name.split()[0] if name else "",
                    "lastname": " ".join(name.split()[1:]) if name and len(name.split()) > 1 else "",
                    "phone": phone
                }
            }
            
            update_response = self._make_request("PATCH", f"/crm/v3/objects/contacts/{contact_id}", update_data)
            if update_response:
                logger.info(f"Contact updated in HubSpot: {contact_id}")
                return str(contact_id)
        else:
            # Nieuw contact aanmaken
            create_data = {
                "properties": {
                    "email": email,
                    "firstname": name.split()[0] if name else "",
                    "lastname": " ".join(name.split()[1:]) if name and len(name.split()) > 1 else "",
                    "phone": phone
                }
            }
            
            create_response = self._make_request("POST", "/crm/v3/objects/contacts", create_data)
            if create_response:
                contact_id = create_response["id"]
                logger.info(f"Contact created in HubSpot: {contact_id}")
                return str(contact_id)
        
        return None
    
    def create_deal(self, amount: float, name: str, stage: str = None, pipeline: str = None) -> Optional[str]:
        """
        Maak een nieuwe deal aan in HubSpot.
        
        Args:
            amount: Bedrag van de deal
            name: Naam van de deal
            stage: Fase van de deal (optioneel, gebruikt default uit env)
            pipeline: Pipeline naam (optioneel, gebruikt default uit env)
            
        Returns:
            Deal ID als string, of None bij fout
        """
        if not self.enabled:
            logger.debug("HubSpot is disabled, skipping deal creation")
            return None
        
        # Haal pipeline ID op
        pipeline_id = self._get_pipeline_id(pipeline or self.pipeline)
        if not pipeline_id:
            logger.error(f"Pipeline '{pipeline or self.pipeline}' not found")
            return None
        
        # Haal stage ID op
        stage_id = self._get_stage_id(pipeline_id, stage or self.stage)
        if not stage_id:
            logger.error(f"Stage '{stage or self.stage}' not found in pipeline '{pipeline or self.pipeline}'")
            return None
        
        create_data = {
            "properties": {
                "amount": str(amount),
                "dealname": name,
                "pipeline": pipeline_id,
                "dealstage": stage_id,
                "closedate": (datetime.now().replace(day=datetime.now().day + 30)).isoformat()
            }
        }
        
        create_response = self._make_request("POST", "/crm/v3/objects/deals", create_data)
        if create_response:
            deal_id = create_response["id"]
            logger.info(f"Deal created in HubSpot: {deal_id}")
            return str(deal_id)
        
        return None
    
    def attach_note(self, deal_id: str, html_url: str) -> bool:
        """
        Voeg een note toe aan een deal met de offerte URL.
        
        Args:
            deal_id: ID van de deal
            html_url: URL naar de HTML offerte
            
        Returns:
            True als succesvol, False anders
        """
        if not self.enabled:
            logger.debug("HubSpot is disabled, skipping note creation")
            return False
        
        note_data = {
            "properties": {
                "hs_note_body": f"Offerte gegenereerd: {html_url}",
                "hs_timestamp": datetime.now().isoformat()
            },
            "associations": [
                {
                    "to": {
                        "id": deal_id
                    },
                    "types": [
                        {
                            "associationCategory": "HUBSPOT_DEFINED",
                            "associationTypeId": 1
                        }
                    ]
                }
            ]
        }
        
        create_response = self._make_request("POST", "/crm/v3/objects/notes", note_data)
        if create_response:
            logger.info(f"Note attached to deal {deal_id} in HubSpot")
            return True
        
        return False
    
    def _get_pipeline_id(self, pipeline_name: str) -> Optional[str]:
        """Haal pipeline ID op op basis van naam."""
        response = self._make_request("GET", "/crm/v3/pipelines/deals")
        if response and "results" in response:
            for pipeline in response["results"]:
                if pipeline["label"].lower() == pipeline_name.lower():
                    return pipeline["id"]
        return None
    
    def _get_stage_id(self, pipeline_id: str, stage_name: str) -> Optional[str]:
        """Haal stage ID op op basis van naam binnen een pipeline."""
        response = self._make_request("GET", f"/crm/v3/pipelines/deals/{pipeline_id}/stages")
        if response and "results" in response:
            for stage in response["results"]:
                if stage["label"].lower() == stage_name.lower():
                    return stage["id"]
        return None
    
    def associate_contact_with_deal(self, contact_id: str, deal_id: str) -> bool:
        """
        Koppel een contact aan een deal.
        
        Args:
            contact_id: ID van het contact
            deal_id: ID van de deal
            
        Returns:
            True als succesvol, False anders
        """
        if not self.enabled:
            logger.debug("HubSpot is disabled, skipping contact-deal association")
            return False
        
        association_data = {
            "inputs": [
                {
                    "from": {
                        "id": contact_id
                    },
                    "to": {
                        "id": deal_id
                    },
                    "types": [
                        {
                            "associationCategory": "HUBSPOT_DEFINED",
                            "associationTypeId": 3  # Contact to Deal
                        }
                    ]
                }
            ]
        }
        
        response = self._make_request("POST", "/crm/v3/objects/contacts/batch/associate/default", association_data)
        if response:
            logger.info(f"Contact {contact_id} associated with deal {deal_id}")
            return True
        
        return False

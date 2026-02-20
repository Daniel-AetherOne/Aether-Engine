#!/usr/bin/env python3
"""
Test script voor HubSpot CRM integratie.
Test de HubSpot client service en CRM router endpoints.
"""

import os
import sys
import requests
import json
from pathlib import Path

# Voeg app directory toe aan Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

def test_hubspot_client():
    """Test de HubSpot client service."""
    print("=== Testing HubSpot Client ===")
    
    try:
        from app.services.hubspot_client import HubSpotClient
        
        # Test client initialisatie
        client = HubSpotClient()
        print(f"✓ HubSpot client geïnitialiseerd")
        print(f"  - Enabled: {client.enabled}")
        print(f"  - Pipeline: {client.pipeline}")
        print(f"  - Stage: {client.stage}")
        print(f"  - Has token: {bool(client.api_token)}")
        
        # Test met disabled state
        if not client.enabled:
            print("  - HubSpot is uitgeschakeld (verwacht gedrag)")
            
            # Test methods returnen None/False wanneer disabled
            contact_id = client.upsert_contact("test@example.com", "Test User", "+31 6 12345678")
            deal_id = client.create_deal(1000.0, "Test Deal")
            note_attached = client.attach_note("123", "http://example.com")
            
            print(f"  - Contact creation (disabled): {contact_id is None}")
            print(f"  - Deal creation (disabled): {deal_id is None}")
            print(f"  - Note attachment (disabled): {note_attached is False}")
        
        print("✓ HubSpot client tests voltooid\n")
        return True
        
    except Exception as e:
        print(f"✗ HubSpot client test gefaald: {str(e)}")
        return False

def test_crm_endpoints():
    """Test de CRM router endpoints."""
    print("=== Testing CRM Endpoints ===")
    
    base_url = "http://localhost:8000"
    
    try:
        # Test CRM status endpoint
        print("Testing GET /crm/status...")
        response = requests.get(f"{base_url}/crm/status", timeout=10)
        
        if response.status_code == 200:
            status_data = response.json()
            print(f"✓ CRM status endpoint werkt")
            print(f"  - HubSpot enabled: {status_data.get('hubspot_enabled')}")
            print(f"  - Pipeline: {status_data.get('pipeline')}")
            print(f"  - Stage: {status_data.get('stage')}")
            print(f"  - Has token: {status_data.get('has_token')}")
        else:
            print(f"✗ CRM status endpoint gefaald: {response.status_code}")
            return False
        
        # Test CRM push endpoint met dummy data
        print("\nTesting POST /crm/push...")
        test_data = {
            "lead": {
                "name": "Test User",
                "email": "test@example.com",
                "phone": "+31 6 12345678",
                "address": "Test Address 123",
                "square_meters": 50.0
            },
            "quote_data": {
                "quote_id": "TEST123",
                "total": 1500.00,
                "html_url": "http://localhost:8000/files/2024-01/TEST123/TEST123.html",
                "pdf_url": "http://localhost:8000/files/2024-01/TEST123/TEST123.pdf",
                "year_month": "2024-01"
            }
        }
        
        response = requests.post(
            f"{base_url}/crm/push",
            json=test_data,
            timeout=10
        )
        
        if response.status_code == 200:
            push_data = response.json()
            print(f"✓ CRM push endpoint werkt")
            print(f"  - Success: {push_data.get('success')}")
            print(f"  - Message: {push_data.get('message')}")
            print(f"  - HubSpot enabled: {push_data.get('hubspot_enabled')}")
            
            if push_data.get('contact_id'):
                print(f"  - Contact ID: {push_data.get('contact_id')}")
            if push_data.get('deal_id'):
                print(f"  - Deal ID: {push_data.get('deal_id')}")
            if push_data.get('note_attached') is not None:
                print(f"  - Note attached: {push_data.get('note_attached')}")
        else:
            print(f"✗ CRM push endpoint gefaald: {response.status_code} - {response.text}")
            return False
        
        print("✓ CRM endpoint tests voltooid\n")
        return True
        
    except requests.exceptions.ConnectionError:
        print("✗ Kan geen verbinding maken met de server. Start de server eerst met: uvicorn app.main:app --reload")
        return False
    except Exception as e:
        print(f"✗ CRM endpoint tests gefaald: {str(e)}")
        return False

def test_quote_with_crm():
    """Test quote creatie met automatische CRM push."""
    print("=== Testing Quote Creation with CRM ===")
    
    base_url = "http://localhost:8000"
    
    try:
        # Test quote creatie endpoint
        print("Testing POST /quote/create...")
        test_data = {
            "lead_id": "TEST_LEAD_001",
            "image_paths": ["data/uploads/test_image.jpg"],
            "m2": 75.0,
            "contactgegevens": {
                "name": "CRM Test User",
                "email": "crmtest@example.com",
                "phone": "+31 6 98765432",
                "address": "CRM Test Address 456"
            }
        }
        
        response = requests.post(
            f"{base_url}/quote/create",
            json=test_data,
            timeout=30
        )
        
        if response.status_code == 200:
            quote_data = response.json()
            print(f"✓ Quote creatie met CRM werkt")
            print(f"  - Success: {quote_data.get('success')}")
            print(f"  - Quote ID: {quote_data.get('quote_id')}")
            print(f"  - Total: €{quote_data.get('total')}")
            print(f"  - Public URL: {quote_data.get('public_url')}")
            print(f"  - Message: {quote_data.get('message')}")
            
            # Check of de offerte bestanden bestaan
            quote_id = quote_data.get('quote_id')
            if quote_id:
                year_month = "2024-01"  # Aanname voor test
                html_path = f"data/offers/{year_month}/{quote_id}/{quote_id}.html"
                pdf_path = f"data/offers/{year_month}/{quote_id}/{quote_id}.pdf"
                
                if Path(html_path).exists():
                    print(f"  - HTML bestand aangemaakt: {html_path}")
                if Path(pdf_path).exists():
                    print(f"  - PDF bestand aangemaakt: {pdf_path}")
        else:
            print(f"✗ Quote creatie gefaald: {response.status_code} - {response.text}")
            return False
        
        print("✓ Quote creatie met CRM tests voltooid\n")
        return True
        
    except requests.exceptions.ConnectionError:
        print("✗ Kan geen verbinding maken met de server. Start de server eerst met: uvicorn app.main:app --reload")
        return False
    except Exception as e:
        print(f"✗ Quote creatie met CRM tests gefaald: {str(e)}")
        return False

def main():
    """Hoofdfunctie voor alle tests."""
    print("HubSpot CRM Integration Tests")
    print("=" * 40)
    
    # Test HubSpot client
    client_success = test_hubspot_client()
    
    # Test CRM endpoints
    endpoints_success = test_crm_endpoints()
    
    # Test quote creatie met CRM
    quote_success = test_quote_with_crm()
    
    # Samenvatting
    print("=" * 40)
    print("Test Samenvatting:")
    print(f"  - HubSpot Client: {'✓' if client_success else '✗'}")
    print(f"  - CRM Endpoints: {'✓' if endpoints_success else '✗'}")
    print(f"  - Quote + CRM: {'✓' if quote_success else '✗'}")
    
    if all([client_success, endpoints_success, quote_success]):
        print("\n🎉 Alle tests geslaagd! HubSpot integratie werkt correct.")
    else:
        print("\n⚠️  Sommige tests gefaald. Controleer de configuratie.")
    
    print("\nOm de server te starten:")
    print("  uvicorn app.main:app --reload")
    print("\nOm de tests te draaien:")
    print("  python test_hubspot.py")

if __name__ == "__main__":
    main()

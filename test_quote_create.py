#!/usr/bin/env python3
"""
Test script voor de nieuwe /quote/create orchestratie endpoint.
Test met 2 testafbeeldingen en m²=40.
"""

import requests
import json
import os
from pathlib import Path

# API base URL
BASE_URL = "http://localhost:8000"

def create_test_images():
    """Maak 2 testafbeeldingen aan voor testing."""
    test_dir = Path("test_images")
    test_dir.mkdir(exist_ok=True)
    
    # Maak een eenvoudige testafbeelding (1x1 pixel PNG)
    from PIL import Image
    import numpy as np
    
    # Testafbeelding 1: Simuleer gipsplaat (lichte kleur)
    img1 = Image.fromarray(np.ones((100, 100, 3), dtype=np.uint8) * 200)
    img1_path = test_dir / "test_gipsplaat.png"
    img1.save(img1_path)
    
    # Testafbeelding 2: Simuleer beton (donkere kleur)
    img2 = Image.fromarray(np.ones((100, 100, 3), dtype=np.uint8) * 100)
    img2_path = test_dir / "test_beton.png"
    img2.save(img2_path)
    
    return [str(img1_path), str(img2_path)]

def test_quote_create():
    """Test de /quote/create endpoint."""
    
    # Maak testafbeeldingen
    print("🔧 Testafbeeldingen aanmaken...")
    image_paths = create_test_images()
    print(f"✅ Testafbeeldingen aangemaakt: {image_paths}")
    
    # Test data
    test_data = {
        "lead_id": "test_lead_123",
        "image_paths": image_paths,
        "m2": 40.0,
        "contactgegevens": {
            "name": "Test Klant",
            "email": "test@example.com",
            "phone": "+31 6 12345678",
            "address": "Teststraat 123, 1234 AB Amsterdam"
        }
    }
    
    print(f"\n🚀 Testen van /quote/create endpoint...")
    print(f"📊 Test data: {json.dumps(test_data, indent=2)}")
    
    try:
        # Roep de endpoint aan
        response = requests.post(
            f"{BASE_URL}/quote/create",
            json=test_data,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"\n📡 Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ SUCCESS! Quote succesvol aangemaakt:")
            print(f"   Quote ID: {result['quote_id']}")
            print(f"   Totaal: €{result['total']}")
            print(f"   Public URL: {result['public_url']}")
            print(f"   Message: {result['message']}")
            
            # Valideer dat total > 0
            if result['total'] > 0:
                print("✅ Totaal is groter dan 0 - Acceptatie criterium gehaald!")
            else:
                print("❌ Totaal is niet groter dan 0")
                
            # Valideer dat public_url bestaat
            if result['public_url']:
                print("✅ Public URL is aanwezig - Acceptatie criterium gehaald!")
            else:
                print("❌ Public URL ontbreekt")
                
        else:
            print(f"❌ ERROR: {response.status_code}")
            print(f"Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Kon geen verbinding maken met de API. Zorg ervoor dat de server draait op http://localhost:8000")
    except Exception as e:
        print(f"❌ Onverwachte fout: {e}")

def test_quote_info(quote_id):
    """Test het ophalen van quote informatie."""
    if not quote_id:
        return
        
    print(f"\n🔍 Testen van quote informatie voor ID: {quote_id}")
    
    try:
        response = requests.get(f"{BASE_URL}/quote/info/{quote_id}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Quote informatie opgehaald:")
            print(f"   HTML URL: {result.get('html_url')}")
            print(f"   PDF URL: {result.get('pdf_url')}")
            print(f"   Exists: {result.get('exists')}")
        else:
            print(f"❌ Kon quote informatie niet ophalen: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Fout bij ophalen quote info: {e}")

if __name__ == "__main__":
    print("🧪 LevelAI SaaS - Quote Create Endpoint Test")
    print("=" * 50)
    
    # Test de hoofdendpoint
    test_quote_create()
    
    print("\n" + "=" * 50)
    print("🏁 Test voltooid!")

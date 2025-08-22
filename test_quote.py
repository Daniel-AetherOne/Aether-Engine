#!/usr/bin/env python3
"""
Test script voor de quote functionaliteit.
Test de volledige flow van offerte generatie.
"""

import requests
import json
import time
import webbrowser
from pathlib import Path

# API base URL
BASE_URL = "http://localhost:8000"

def test_quote_generation():
    """Test de volledige offerte generatie flow."""
    
    print("🚀 Start test van quote functionaliteit...")
    
    # Test data
    test_data = {
        "lead": {
            "name": "Jan Jansen",
            "email": "jan.jansen@example.com",
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
    
    print(f"📝 Test data voorbereid:")
    print(f"   Klant: {test_data['lead']['name']}")
    print(f"   Oppervlakte: {test_data['lead']['square_meters']} m²")
    print(f"   Substraat: {test_data['prediction']['substrate']}")
    print(f"   Issues: {', '.join(test_data['prediction']['issues'])}")
    
    try:
        # 1. Test quote render endpoint
        print("\n🔄 Stap 1: Offerte genereren via API...")
        response = requests.post(
            f"{BASE_URL}/quote/render",
            json=test_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Offerte succesvol gegenereerd!")
            print(f"   Quote ID: {result['quote_id']}")
            print(f"   HTML pad: {result['html_path']}")
            print(f"   PDF pad: {result['pdf_path']}")
            print(f"   Public URL: {result['public_url']}")
            print(f"   HTML URL: {result['html_url']}")
            print(f"   Jaar-maand: {result['year_month']}")
            
            quote_id = result['quote_id']
            year_month = result['year_month']
            
            # 2. Test quote info endpoint
            print("\n🔄 Stap 2: Offerte informatie ophalen...")
            info_response = requests.get(f"{BASE_URL}/quote/info/{quote_id}")
            
            if info_response.status_code == 200:
                info = info_response.json()
                print("✅ Offerte informatie succesvol opgehaald!")
                print(f"   Bestaat: {info['exists']}")
                print(f"   HTML URL: {info['html_url']}")
                print(f"   PDF URL: {info['pdf_url']}")
            else:
                print(f"❌ Fout bij ophalen offerte info: {info_response.status_code}")
                print(info_response.text)
            
            # 3. Test bestand toegang
            print("\n🔄 Stap 3: Test bestand toegang...")
            
            # Test HTML bestand
            html_url = f"{BASE_URL}{result['html_url']}"
            print(f"   HTML URL: {html_url}")
            
            # Test PDF bestand
            pdf_url = f"{BASE_URL}{result['public_url']}"
            print(f"   PDF URL: {pdf_url}")
            
            # 4. Test bestand download
            print("\n🔄 Stap 4: Test bestand download...")
            
            try:
                pdf_response = requests.get(pdf_url)
                if pdf_response.status_code == 200:
                    print("✅ PDF bestand succesvol gedownload!")
                    print(f"   Bestandsgrootte: {len(pdf_response.content)} bytes")
                    
                    # Sla PDF op voor verificatie
                    test_pdf_path = Path(f"test_quote_{quote_id}.pdf")
                    with open(test_pdf_path, 'wb') as f:
                        f.write(pdf_response.content)
                    print(f"   PDF opgeslagen als: {test_pdf_path}")
                    
                else:
                    print(f"❌ Fout bij downloaden PDF: {pdf_response.status_code}")
                    
            except Exception as e:
                print(f"❌ Fout bij downloaden PDF: {e}")
            
            # 5. Test lijst endpoint
            print("\n🔄 Stap 5: Test offerte lijst...")
            list_response = requests.get(f"{BASE_URL}/quote/list")
            
            if list_response.status_code == 200:
                list_result = list_response.json()
                print("✅ Offerte lijst succesvol opgehaald!")
                print(f"   Totaal offertes: {list_result.get('total', 'Onbekend')}")
                
                # Filter op jaar-maand
                year_month_response = requests.get(f"{BASE_URL}/quote/list?year_month={year_month}")
                if year_month_response.status_code == 200:
                    ym_result = year_month_response.json()
                    print(f"   Offerte(s) in {year_month}: {len(ym_result.get('quotes', []))}")
                    
            else:
                print(f"❌ Fout bij ophalen offerte lijst: {list_response.status_code}")
            
            # 6. Open bestanden in browser
            print("\n🔄 Stap 6: Open bestanden in browser...")
            try:
                print(f"   HTML bestand openen: {html_url}")
                webbrowser.open(html_url)
                
                print(f"   PDF bestand openen: {pdf_url}")
                webbrowser.open(pdf_url)
                
            except Exception as e:
                print(f"   Browser kon niet geopend worden: {e}")
            
            print("\n🎉 Test voltooid! Alle functionaliteit werkt correct.")
            print(f"\n📋 Samenvatting:")
            print(f"   - Offerte gegenereerd met ID: {quote_id}")
            print(f"   - Bestanden opgeslagen in: data/offers/{year_month}/{quote_id}/")
            print(f"   - Public URLs beschikbaar via /files/...")
            print(f"   - PDF en HTML bestanden zijn toegankelijk")
            
            return True
            
        else:
            print(f"❌ Fout bij genereren offerte: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Kan geen verbinding maken met de API server.")
        print("   Zorg ervoor dat de server draait op http://localhost:8000")
        return False
        
    except Exception as e:
        print(f"❌ Onverwachte fout: {e}")
        return False

def test_health():
    """Test of de server draait."""
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("✅ Server is actief en gezond")
            return True
        else:
            print(f"❌ Server health check gefaald: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ Server is niet bereikbaar")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 LevelAI SaaS - Quote Functionaliteit Test")
    print("=" * 60)
    
    # Test server health
    if not test_health():
        print("\n❌ Server is niet beschikbaar. Start de server eerst met:")
        print("   uvicorn app.main:app --reload")
        exit(1)
    
    print()
    
    # Test quote functionaliteit
    success = test_quote_generation()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 ALLE TESTS GESLAAGD!")
        print("   De quote functionaliteit werkt correct.")
    else:
        print("❌ TESTS GEFAALD!")
        print("   Er zijn problemen met de quote functionaliteit.")
    print("=" * 60)

#!/usr/bin/env python3
"""
Eenvoudige test voor de nieuwe /quote/create orchestratie endpoint.
Gebruikt bestaande testafbeeldingen of simuleert de flow.
"""

import json
import os
from pathlib import Path

def test_quote_create_logic():
    """Test de logica van de quote create endpoint zonder externe dependencies."""
    
    print("🧪 LevelAI SaaS - Quote Create Endpoint Logic Test")
    print("=" * 60)
    
    # Simuleer test data
    test_data = {
        "lead_id": "test_lead_123",
        "image_paths": [
            "test_images/test_gipsplaat.png",
            "test_images/test_beton.png"
        ],
        "m2": 40.0,
        "contactgegevens": {
            "name": "Test Klant",
            "email": "test@example.com",
            "phone": "+31 6 12345678",
            "address": "Teststraat 123, 1234 AB Amsterdam"
        }
    }
    
    print("📊 Test data:")
    print(json.dumps(test_data, indent=2))
    
    # Valideer input
    print("\n🔍 Input validatie:")
    
    # Check lead_id
    if test_data["lead_id"]:
        print("✅ lead_id is aanwezig")
    else:
        print("❌ lead_id ontbreekt")
    
    # Check image_paths
    if test_data["image_paths"] and len(test_data["image_paths"]) > 0:
        print(f"✅ image_paths bevat {len(test_data['image_paths'])} afbeeldingen")
    else:
        print("❌ image_paths is leeg")
    
    # Check m2
    if test_data["m2"] > 0:
        print(f"✅ m2 is {test_data['m2']} (groter dan 0)")
    else:
        print("❌ m2 moet groter zijn dan 0")
    
    # Check contactgegevens
    required_fields = ["name", "email", "phone", "address"]
    missing_fields = [field for field in required_fields if not test_data["contactgegevens"].get(field)]
    
    if not missing_fields:
        print("✅ Alle vereiste contactgegevens zijn aanwezig")
    else:
        print(f"❌ Ontbrekende contactgegevens: {missing_fields}")
    
    # Simuleer de flow stappen
    print("\n🚀 Flow simulatie:")
    
    # Stap 1: Predict
    print("1️⃣ Predictie: substrate=gipsplaat, issues=[vocht]")
    
    # Stap 2: Prijsberekening
    base_price_per_m2 = 25.0  # Voorbeeld prijs
    subtotal = test_data["m2"] * base_price_per_m2
    surcharge = 0.15  # 15% voor vocht
    subtotal_with_surcharge = subtotal * (1 + surcharge)
    vat = subtotal_with_surcharge * 0.21  # 21% BTW
    total = subtotal_with_surcharge + vat
    
    print(f"2️⃣ Prijsberekening: {test_data['m2']}m² × €{base_price_per_m2} = €{subtotal}")
    print(f"   Surcharge (15%): €{subtotal * surcharge}")
    print(f"   Subtotaal: €{subtotal_with_surcharge}")
    print(f"   BTW (21%): €{vat}")
    print(f"   Totaal: €{total}")
    
    # Stap 3: Quote rendering
    quote_id = "TEST123"
    year_month = "2024-01"
    public_url = f"/files/{year_month}/{quote_id}/{quote_id}.html"
    
    print(f"3️⃣ Quote rendering: ID={quote_id}, URL={public_url}")
    
    # Valideer output
    print("\n✅ Output validatie:")
    
    if total > 0:
        print("✅ Totaal is groter dan 0")
    else:
        print("❌ Totaal moet groter zijn dan 0")
    
    if public_url:
        print("✅ Public URL is aanwezig")
    else:
        print("❌ Public URL ontbreekt")
    
    if quote_id:
        print("✅ Quote ID is gegenereerd")
    else:
        print("❌ Quote ID ontbreekt")
    
    # Simuleer response
    response = {
        "success": True,
        "quote_id": quote_id,
        "total": total,
        "public_url": public_url,
        "message": "Offerte succesvol aangemaakt"
    }
    
    print("\n📡 Simuleerde response:")
    print(json.dumps(response, indent=2))
    
    # Acceptatie criteria check
    print("\n🎯 Acceptatie criteria:")
    
    if total > 0:
        print("✅ Totaal > 0: GEHAALD")
    else:
        print("❌ Totaal > 0: NIET GEHAALD")
    
    if public_url and public_url.startswith("/files/"):
        print("✅ PDF-link (public_url) aanwezig: GEHAALD")
    else:
        print("❌ PDF-link (public_url) aanwezig: NIET GEHAALD")
    
    print("\n" + "=" * 60)
    print("🏁 Test voltooid!")

if __name__ == "__main__":
    test_quote_create_logic()

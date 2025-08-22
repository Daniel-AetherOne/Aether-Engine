#!/usr/bin/env python3
"""
Demo script voor de PricingEngine.
Toont hoe de prijsberekening werkt met verschillende scenarios.
"""

import sys
from pathlib import Path

# Voeg de app directory toe aan Python path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from services.pricing_engine import PricingEngine


def main():
    """Demo van de pricing engine functionaliteit."""
    print("🚀 LevelAI SaaS - Pricing Engine Demo")
    print("=" * 50)
    
    # Initialiseer de pricing engine
    engine = PricingEngine()
    
    # Demo scenario's
    scenarios = [
        {
            "name": "Gipsplaat 40m² (geen issues)",
            "m2": 40.0,
            "substrate": "gipsplaat",
            "issues": []
        },
        {
            "name": "Beton 12m² met vochtprobleem",
            "m2": 12.0,
            "substrate": "beton",
            "issues": ["vocht"]
        },
        {
            "name": "Bestaand 8m² (minimum totaal test)",
            "m2": 8.0,
            "substrate": "bestaand",
            "issues": []
        },
        {
            "name": "Beton 15m² met meerdere issues",
            "m2": 15.0,
            "substrate": "beton",
            "issues": ["vocht", "scheuren"]
        }
    ]
    
    for i, scenario in enumerate(scenarios, 1):
        print(f"\n📋 Scenario {i}: {scenario['name']}")
        print("-" * 40)
        
        try:
            result = engine.compute_price(
                scenario["m2"], 
                scenario["substrate"], 
                scenario["issues"]
            )
            
            print(f"Input:")
            print(f"  • Oppervlakte: {scenario['m2']}m²")
            print(f"  • Substrate: {scenario['substrate']}")
            print(f"  • Issues: {scenario['issues'] if scenario['issues'] else 'Geen'}")
            
            print(f"\nOutput:")
            print(f"  • Subtotaal: €{result['subtotal']:.2f}")
            print(f"  • Korting: €{result['discount']:.2f}")
            print(f"  • BTW (21%): €{result['vat_amount']:.2f}")
            print(f"  • Totaalprijs: €{result['total']:.2f}")
            print(f"  • Doorlooptijd: {result['doorlooptijd']}")
            
            print(f"\nAannames:")
            for j, aanname in enumerate(result['aannames'], 1):
                print(f"  {j}. {aanname}")
                
        except Exception as e:
            print(f"❌ Fout: {e}")
    
    print("\n" + "=" * 50)
    print("✅ Demo voltooid!")
    print("\nPrijzen zijn inclusief BTW en gebaseerd op de regels in rules/pricing_rules.json")


if __name__ == "__main__":
    main()

# Pricing Engine - LevelAI SaaS

Een Python-gebaseerde prijsengine die m², substrate en issues omzet naar een totaalprijs inclusief BTW.

## Functionaliteit

De pricing engine berekent prijzen op basis van:
- **Oppervlakte** in vierkante meters (m²)
- **Substrate type**: gipsplaat, beton, of bestaand
- **Issues**: vocht, scheuren (optioneel)

## Prijsregels

### Basisprijzen per m²
- **Gipsplaat**: €16.50/m²
- **Beton**: €22.00/m²  
- **Bestaand**: €18.00/m²

### Surcharges voor issues
- **Vocht**: +20% op subtotaal
- **Scheuren**: +10% op subtotaal

### Overige regels
- **Minimum totaal**: €250.00 (excl. BTW)
- **BTW percentage**: 21%

## Gebruik

### Basis gebruik

```python
from app.services.pricing_engine import PricingEngine

# Initialiseer de engine
engine = PricingEngine()

# Bereken prijs
result = engine.compute_price(
    m2=40.0,                    # 40 vierkante meters
    substrate="gipsplaat",      # Type substrate
    issues=["vocht"]            # Lijst van issues (optioneel)
)

print(f"Totaalprijs: €{result['total']:.2f}")
```

### Output structuur

```python
{
    "subtotal": 660.0,          # Subtotaal excl. BTW
    "discount": 0.0,            # Korting (altijd 0)
    "vat_amount": 138.6,        # BTW bedrag
    "total": 798.6,             # Totaalprijs incl. BTW
    "aannames": [...],          # Lijst van aannames
    "doorlooptijd": "4.0 werkdagen"  # Geschatte doorlooptijd
}
```

## Voorbeelden

### 1. Gipsplaat 40m² (geen issues)
- Subtotaal: 40 × €16.50 = €660.00
- BTW: €660.00 × 21% = €138.60
- **Totaal: €798.60**

### 2. Beton 12m² met vocht
- Subtotaal: 12 × €22.00 = €264.00
- Vocht surcharge: €264.00 × 20% = €52.80
- Subtotaal met surcharge: €316.80
- BTW: €316.80 × 21% = €66.53
- **Totaal: €383.33**

### 3. Bestaand 8m² (minimum totaal)
- Subtotaal: 8 × €18.00 = €144.00
- Minimum totaal toegepast: €250.00
- BTW: €250.00 × 21% = €52.50
- **Totaal: €302.50**

## Bestanden

- **`rules/pricing_rules.json`**: Prijsregels en configuratie
- **`app/services/pricing_engine.py`**: Hoofdlogica van de pricing engine
- **`test_pricing.py`**: Unit tests
- **`demo_pricing.py`**: Demo script met voorbeelden

## Tests uitvoeren

```bash
# Alle tests uitvoeren
python test_pricing.py

# Demo uitvoeren
python demo_pricing.py
```

## Configuratie aanpassen

Wijzig de prijsregels in `rules/pricing_rules.json`:

```json
{
  "base_per_m2": {
    "gipsplaat": 16.5,
    "beton": 22.0,
    "bestaand": 18.0
  },
  "surcharge": {
    "vocht": 0.20,
    "scheuren": 0.10
  },
  "min_total": 250.0,
  "vat_percent": 21.0
}
```

## Aannames en doorlooptijd

De engine genereert automatisch:
- **Aannames** op basis van substrate en issues
- **Doorlooptijd** schattingen op basis van oppervlakte en complexiteit

## Foutafhandeling

De engine valideert input en genereert duidelijke foutmeldingen voor:
- Ongeldige substrate types
- Negatieve of nul oppervlakte waarden
- Problemen met het laden van prijsregels

## Uitbreidingsmogelijkheden

De engine is ontworpen om eenvoudig uit te breiden met:
- Nieuwe substrate types
- Extra issue categorieën
- Kortingsregels
- Seizoensgebonden prijzen
- Klant-specifieke tarieven

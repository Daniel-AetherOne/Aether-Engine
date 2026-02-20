# Quote Create Orchestratie Endpoint

## Overzicht

De nieuwe `/quote/create` endpoint is een orchestratie-endpoint die de volledige flow doorloopt voor het creeëren van een offerte:

1. **Predict** → Analyseer afbeeldingen voor substrate en issues
2. **Compute Price** → Bereken prijs op basis van m², substrate en issues  
3. **Render Quote** → Genereer HTML/PDF offerte
4. **Response** → Retourneer quote_id, total en public_url

## Endpoint Details

### Route
```
POST /quote/create
```

### Request Body
```json
{
  "lead_id": "string",
  "image_paths": ["string"],
  "m2": 40.0,
  "contactgegevens": {
    "name": "string",
    "email": "string", 
    "phone": "string",
    "address": "string"
  }
}
```

### Response
```json
{
  "success": true,
  "quote_id": "ABC12345",
  "total": 1250.50,
  "public_url": "/files/2024-01/ABC12345/ABC12345.html",
  "message": "Offerte succesvol aangemaakt"
}
```

## Flow Stappen

### 1. Predict (Substrate & Issues)
- Analyseert geüploade afbeeldingen
- Bepaalt type substrate (gipsplaat, beton, bestaand)
- Detecteert issues (vocht, scheuren)
- Retourneert confidence scores

### 2. Compute Price
- Basisprijs per m² op basis van substrate
- Surcharges voor gedetecteerde issues
- BTW berekening
- Minimum totaal validatie

### 3. Render Quote
- Genereert unieke quote_id
- Maakt jaar-maand directory structuur
- Rendert HTML template met alle data
- Slaat op in `data/offers/{YYYY-MM}/{quote_id}/`

### 4. Response
- `quote_id`: Unieke identifier voor de offerte
- `total`: Totaalprijs in euro's
- `public_url`: Publiek toegankelijke URL naar de offerte

## Logging

Alle stappen worden gelogd met `lead_id` en `quote_id` voor volledige traceerbaarheid:

```
INFO: Start quote creatie voor lead_id: test_lead_123
INFO: Stap 1: Start predictie voor lead_id: test_lead_123
INFO: Predictie voltooid voor lead_id: test_lead_123 - Substrate: gipsplaat, Issues: ['vocht']
INFO: Stap 2: Start prijsberekening voor lead_id: test_lead_123
INFO: Prijsberekening voltooid voor lead_id: test_lead_123 - Totaal: €1250.50
INFO: Stap 3: Start offerte rendering voor lead_id: test_lead_123
INFO: Offerte rendering voltooid voor lead_id: test_lead_123 - Quote ID: ABC12345
INFO: Quote creatie succesvol voltooid - Lead ID: test_lead_123, Quote ID: ABC12345
```

## Bestandsstructuur

Na succesvolle uitvoering wordt de volgende structuur aangemaakt:

```
data/
├── offers/
│   └── 2024-01/           # Jaar-maand
│       └── ABC12345/      # Quote ID
│           └── ABC12345.html  # HTML offerte
```

## Validatie

- `lead_id`: Verplicht, mag niet leeg zijn
- `image_paths`: Verplicht, mag niet leeg zijn
- `m2`: Verplicht, moet groter zijn dan 0
- `contactgegevens`: Verplicht, moet alle velden bevatten

## Error Handling

- **400 Bad Request**: Ongeldige input parameters
- **500 Internal Server Error**: Fouten tijdens verwerking

Alle fouten worden gelogd met context van `lead_id`.

## Testen

### Eenvoudige Test
```bash
python test_quote_create_simple.py
```

### Volledige API Test
```bash
# Start de server eerst
uvicorn app.main:app --reload

# In een andere terminal
python test_quote_create.py
```

## Acceptatie Criteria

✅ **Met 2 testafbeeldingen en m²=40:**
- Komt er een PDF-link terug (public_url)
- Total > 0

## Dependencies

- `app.services.predictor.SimplePredictor`
- `app.services.pricing_engine.PricingEngine`  
- `app.services.quote_renderer_simple.QuoteRendererSimple`

## Integratie

De endpoint is geïntegreerd in de bestaande FastAPI applicatie via:
- `app/routers/quote.py` - Router definitie
- `app/main.py` - App mounting

## Volgende Stappen

- PDF generatie toevoegen
- Email integratie voor offerte verzending
- Database opslag voor offerte metadata
- Webhook notificaties

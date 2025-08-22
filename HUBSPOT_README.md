# HubSpot CRM Integratie

Deze module voegt HubSpot CRM integratie toe aan de LevelAI SaaS applicatie. Na het renderen van een offerte wordt automatisch een contact en deal aangemaakt in HubSpot met een note die verwijst naar de offerte URL.

## Functies

### HubSpot Client Service (`app/services/hubspot_client.py`)

- **`upsert_contact(email, name, phone)`**: Maakt een nieuw contact aan of update bestaand contact
- **`create_deal(amount, name, stage, pipeline)`**: Maakt een nieuwe deal aan voor de offerte
- **`attach_note(deal_id, html_url)`**: Voegt een note toe aan de deal met de offerte URL
- **`associate_contact_with_deal(contact_id, deal_id)`**: Koppelt het contact aan de deal

### CRM Router (`app/routers/crm.py`)

- **`POST /crm/push`**: Endpoint voor handmatige CRM push
- **`GET /crm/status`**: Status van HubSpot configuratie

### Automatische Integratie

De HubSpot integratie wordt automatisch aangeroepen na:
- Quote creatie via `/quote/create`
- Quote rendering via `/quote/render`

## Configuratie

### Environment Variabelen

Voeg deze variabelen toe aan je `.env` bestand:

```bash
# HubSpot CRM Integration
HUBSPOT_ENABLED=false
HUBSPOT_TOKEN=your-hubspot-api-token
PIPELINE=default
STAGE=appointmentscheduled
```

### Configuratie Opties

- **`HUBSPOT_ENABLED`**: `true` om HubSpot te activeren, `false` voor lokale modus
- **`HUBSPOT_TOKEN`**: Je HubSpot API token (Private App token)
- **`PIPELINE`**: Naam van de deal pipeline in HubSpot
- **`STAGE`**: Naam van de deal stage in HubSpot

## Gebruik

### Lokale Modus (HUBSPOT_ENABLED=false)

Wanneer HubSpot is uitgeschakeld:
- Alle CRM calls worden lokaal verwerkt
- Geen externe API calls naar HubSpot
- Logging toont wat er zou gebeuren
- Quote creatie werkt normaal door

### HubSpot Modus (HUBSPOT_ENABLED=true)

Wanneer HubSpot is ingeschakeld:
- Contact wordt aangemaakt/geupdate in HubSpot
- Deal wordt aangemaakt met het juiste bedrag
- Contact wordt gekoppeld aan de deal
- Note wordt toegevoegd met offerte URL
- Alle acties worden gelogd

## API Endpoints

### POST /crm/push

Handmatige CRM push voor bestaande offertes.

**Request:**
```json
{
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
```

**Response:**
```json
{
  "success": true,
  "message": "Lead en offerte succesvol gepusht naar HubSpot. Contact: 123, Deal: 456",
  "hubspot_enabled": true,
  "contact_id": "123",
  "deal_id": "456",
  "note_attached": true
}
```

### GET /crm/status

Status van HubSpot configuratie.

**Response:**
```json
{
  "hubspot_enabled": true,
  "pipeline": "default",
  "stage": "appointmentscheduled",
  "has_token": true
}
```

## Workflow

1. **Quote Creatie**: Gebruiker maakt offerte aan via `/quote/create`
2. **AI Predictie**: Substraat en issues worden voorspeld
3. **Prijsberekening**: Totaal bedrag wordt berekend
4. **Offerte Rendering**: HTML en PDF worden gegenereerd
5. **Automatische CRM Push**:
   - Contact wordt aangemaakt/geupdate in HubSpot
   - Deal wordt aangemaakt met het totaal bedrag
   - Contact wordt gekoppeld aan de deal
   - Note wordt toegevoegd met offerte URL

## Foutafhandeling

- CRM fouten blokkeren **niet** de quote creatie
- Alle CRM acties worden gelogd
- Bij fouten wordt een waarschuwing gelogd
- De applicatie blijft functioneren ook als HubSpot niet beschikbaar is

## Testen

### Test Script

Gebruik het test script om de integratie te testen:

```bash
python test_hubspot.py
```

### Handmatige Test

1. Start de server: `uvicorn app.main:app --reload`
2. Test CRM status: `GET /crm/status`
3. Test CRM push: `POST /crm/push`
4. Test quote creatie: `POST /quote/create`

## HubSpot Setup

### Private App Aanmaken

1. Ga naar HubSpot Settings > Account Setup > Integrations > Private Apps
2. Klik "Create private app"
3. Geef je app een naam (bijv. "LevelAI Integration")
4. Selecteer de volgende scopes:
   - **Contacts**: Read & Write
   - **Deals**: Read & Write
   - **Notes**: Read & Write
5. Genereer de API token
6. Kopieer de token naar je `.env` bestand

### Pipeline & Stage Configuratie

1. Ga naar HubSpot Settings > Objects > Deals > Pipelines
2. Maak een nieuwe pipeline aan of gebruik bestaande
3. Voeg stages toe (bijv. "Appointment Scheduled", "Quote Sent", "Closed Won")
4. Update je `.env` bestand met de juiste pipeline en stage namen

## Troubleshooting

### Veelvoorkomende Problemen

1. **"Pipeline not found"**: Controleer of de pipeline naam exact overeenkomt
2. **"Stage not found"**: Controleer of de stage naam exact overeenkomt
3. **"Unauthorized"**: Controleer je API token en scopes
4. **"Rate limit exceeded"**: HubSpot heeft rate limiting, wacht even en probeer opnieuw

### Debugging

- Zet logging level op INFO of DEBUG
- Controleer de server logs voor CRM acties
- Gebruik `/crm/status` om configuratie te controleren
- Test met `HUBSPOT_ENABLED=false` eerst

## Afhankelijkheden

- `requests>=2.31.0`: Voor HTTP calls naar HubSpot API
- `python-dotenv`: Voor environment variabelen (al aanwezig)

## Toekomstige Uitbreidingen

- Email notificaties bij CRM updates
- Webhook integratie voor real-time updates
- Deal tracking en follow-up reminders
- Analytics en rapportage integratie
- Multi-tenant HubSpot accounts

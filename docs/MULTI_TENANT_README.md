# Multi-Tenant Functionaliteit - LevelAI SaaS

Deze applicatie is volledig multi-tenant ready gemaakt met gescheiden storage, branding en configuratie per tenant.

## 🏗️ Architectuur

### Tenant Resolutie
- **X-Tenant Header**: Primaire methode voor tenant identificatie
- **Subdomain Fallback**: Automatische tenant detectie via subdomain
- **Default Tenant**: Fallback naar "default" tenant als geen tenant gespecificeerd

### Storage Structuur
```
data/
├── uploads/
│   ├── default/
│   ├── company_a/
│   └── company_b/
└── offers/
    ├── default/
    ├── company_a/
    └── company_b/
```

## 🔧 Configuratie

### Tenant Instellingen
Elke tenant heeft de volgende configuratie:

```json
{
  "tenant_id": "company_a",
  "company_name": "Company A B.V.",
  "logo_url": "https://example.com/logo_a.png",
  "hubspot_token": "pat-company-a-token",
  "pipeline": "Company A Pipeline",
  "stage": "New Lead",
  "primary_color": "#dc2626",
  "secondary_color": "#991b1b"
}
```

### Standaard Tenants
- **default**: LevelAI SaaS (fallback tenant)
- **company_a**: Company A B.V. (rood thema)
- **company_b**: Company B Ltd. (groen thema)

## 📡 API Endpoints

### Tenant Management
- `GET /tenants` - Lijst alle beschikbare tenants
- `GET /tenant/{tenant_id}` - Tenant-specifieke informatie
- `GET /tenant` - Tenant management endpoints

### Intake (Tenant-Aware)
- `GET /intake/form` - Intake formulier met tenant branding
- `POST /intake/` - Intake submission met tenant-aware storage
- `GET /intake/stats/{tenant_id}` - Tenant-specifieke statistieken
- `GET /intake/leads` - Lijst leads voor huidige tenant

### Quote (Tenant-Aware)
- `POST /quote/create` - Volledige quote creatie flow
- `POST /quote/render` - Quote rendering met tenant branding
- `GET /quote/info/{quote_id}` - Quote informatie per tenant
- `GET /quote/list` - Lijst quotes per tenant
- `DELETE /quote/{quote_id}` - Verwijder quote per tenant

## 🎨 Tenant Branding

### Intake Form
- Dynamische bedrijfsnaam in titel en header
- Tenant-specifieke kleuren (primary/secondary)
- Logo weergave (indien geconfigureerd)
- Tenant informatie in formulier

### Quote PDF
- Bedrijfsnaam en logo in header
- Tenant-specifieke kleuren voor styling
- Dynamische contactgegevens
- Tenant branding in footer

## 🔐 Dependencies

### resolve_tenant()
```python
async def resolve_tenant(
    request: Request,
    x_tenant: Optional[str] = Header(None, alias="X-Tenant")
) -> str
```
Resolveert tenant uit header of subdomain, valideert bestaan.

### get_tenant_settings()
```python
async def get_tenant_settings(tenant_id: str = Depends(resolve_tenant))
```
Haalt tenant configuratie op voor gebruik in route handlers.

### get_tenant_storage_path()
```python
async def get_tenant_storage_path(
    base_path: str,
    tenant_id: str = Depends(resolve_tenant)
)
```
Genereert tenant-specifieke storage paden.

## 📝 Gebruik

### 1. Tenant Specificeren
```bash
# Via X-Tenant header
curl -H "X-Tenant: company_a" http://localhost:8000/intake/form

# Via subdomain (indien geconfigureerd)
curl http://company_a.localhost:8000/intake/form
```

### 2. Quote Aanmaken
```bash
curl -X POST "http://localhost:8000/quote/render" \
  -H "X-Tenant: company_a" \
  -H "Content-Type: application/json" \
  -d '{
    "lead": {
      "name": "John Doe",
      "email": "john@example.com",
      "phone": "+31 6 12345678",
      "address": "Hoofdstraat 123, Amsterdam",
      "square_meters": 150.5
    },
    "prediction": {
      "substrate": "gipsplaat",
      "issues": ["vocht"],
      "confidences": {
        "gipsplaat": 0.95,
        "vocht": 0.87
      }
    }
  }'
```

### 3. Tenant-Specifieke Data Ophalen
```bash
# Quotes voor specifieke tenant
curl -H "X-Tenant: company_a" http://localhost:8000/quote/list

# Tenant statistieken
curl -H "X-Tenant: company_a" http://localhost:8000/intake/stats/company_a
```

## 🧪 Testen

### Test Script Uitvoeren
```bash
python test_multi_tenant.py
```

### Handmatige Tests
1. **Start applicatie**: `uvicorn app.main:app --reload`
2. **Test tenant A**: `curl -H "X-Tenant: company_a" http://localhost:8000/tenant/company_a`
3. **Test tenant B**: `curl -H "X-Tenant: company_b" http://localhost:8000/tenant/company_b`
4. **Vergelijk storage**: Controleer `data/uploads/company_a/` vs `data/uploads/company_b/`

## 🔍 Logging

Alle tenant-activiteiten worden gelogd met tenant context:

```
[TENANT:company_a:Company A B.V.] Quote created for lead_id: abc123
[TENANT:company_b:Company B Ltd.] Intake submitted for John Doe (john@example.com) - 3 files uploaded
```

## 🚀 Uitbreidingen

### Nieuwe Tenant Toevoegen
1. Voeg tenant toe aan `tenant_config.json`
2. Herstart applicatie
3. Directories worden automatisch aangemaakt

### Custom Tenant Branding
1. Pas `TenantSettings` model aan
2. Update templates met nieuwe velden
3. Voeg CSS variabelen toe voor styling

### Database Integratie
1. Vervang in-memory storage met database
2. Voeg tenant_id toe aan alle modellen
3. Implementeer tenant-aware queries

## ⚠️ Beperkingen

- **In-Memory Storage**: Tenant configuratie wordt in-memory geladen
- **File-Based**: Geen database integratie (nog)
- **Single Instance**: Geen horizontale schaling (nog)
- **No Auth**: Geen authenticatie/autorisatie (nog)

## 🔮 Toekomstige Verbeteringen

- [ ] Database integratie voor tenant configuratie
- [ ] Tenant authenticatie en autorisatie
- [ ] Horizontale schaling ondersteuning
- [ ] Tenant-specifieke API rate limiting
- [ ] Tenant analytics en monitoring
- [ ] Multi-tenant admin dashboard

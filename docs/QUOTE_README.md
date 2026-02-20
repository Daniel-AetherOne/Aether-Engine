# Quote Functionaliteit - LevelAI SaaS

Deze module biedt een complete oplossing voor het genereren van professionele offertes in HTML en PDF formaat.

## 🚀 Functionaliteiten

- **Automatische offerte generatie** op basis van lead, prediction en pricing data
- **Professionele HTML templates** met moderne styling
- **PDF export** via WeasyPrint voor print-optimale output
- **Gestructureerde opslag** in `data/offers/{yyyy-mm}/{quote_id}/`
- **Public toegang** via `/files/...` endpoints
- **REST API** voor alle operaties

## 📁 Bestandsstructuur

```
app/
├── templates/
│   └── quote.html              # HTML template voor offertes
├── services/
│   └── quote_renderer.py       # Service voor offerte rendering
└── routers/
    └── quote.py                # API endpoints voor offertes

data/
└── offers/                     # Opgeslagen offertes
    └── 2024-01/               # Jaar-maand directories
        └── ABC12345/           # Quote ID directories
            ├── ABC12345.html   # HTML versie
            └── ABC12345.pdf    # PDF versie
```

## 🛠️ Installatie

### Dependencies

De volgende packages zijn vereist (al toegevoegd aan `pyproject.toml`):

```bash
pip install jinja2 weasyprint
```

### WeasyPrint Installatie

WeasyPrint kan soms problemen hebben met system dependencies. Voor Windows:

```bash
# Via conda (aanbevolen)
conda install -c conda-forge weasyprint

# Of via pip met pre-compiled wheels
pip install weasyprint
```

Voor Linux/macOS:
```bash
pip install weasyprint
```

## 🔧 Configuratie

### Template Directory

De template directory wordt automatisch gedetecteerd, maar kan aangepast worden:

```python
quote_renderer = QuoteRenderer(
    templates_dir="app/templates",
    offers_dir="data/offers"
)
```

### Static Files Mount

De offers directory wordt automatisch gemount op `/files` in `main.py`:

```python
app.mount("/files", StaticFiles(directory=str(DATA_DIR)), name="files")
```

## 📡 API Endpoints

### 1. Offerte Genereren

**POST** `/quote/render`

Genereert een nieuwe offerte op basis van lead en prediction data.

**Request Body:**
```json
{
  "lead": {
    "name": "Jan Jansen",
    "email": "jan@example.com",
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
```

**Response:**
```json
{
  "success": true,
  "quote_id": "ABC12345",
  "html_path": "data/offers/2024-01/ABC12345/ABC12345.html",
  "pdf_path": "data/offers/2024-01/ABC12345/ABC12345.pdf",
  "public_url": "/files/2024-01/ABC12345/ABC12345.pdf",
  "html_url": "/files/2024-01/ABC12345/ABC12345.html",
  "year_month": "2024-01",
  "message": "Offerte succesvol gegenereerd"
}
```

### 2. Offerte Informatie

**GET** `/quote/info/{quote_id}`

Haalt informatie op over een specifieke offerte.

**Response:**
```json
{
  "quote_id": "ABC12345",
  "year_month": "2024-01",
  "html_path": "data/offers/2024-01/ABC12345/ABC12345.html",
  "pdf_path": "data/offers/2024-01/ABC12345/ABC12345.pdf",
  "html_url": "/files/2024-01/ABC12345/ABC12345.html",
  "pdf_url": "/files/2024-01/ABC12345/ABC12345.pdf",
  "exists": true
}
```

### 3. Offerte Lijst

**GET** `/quote/list`

Lijst alle offertes op.

**Query Parameters:**
- `year_month` (optioneel): Filter op jaar-maand (format: YYYY-MM)

**Response:**
```json
{
  "quotes": [
    {
      "quote_id": "ABC12345",
      "year_month": "2024-01",
      "html_url": "/files/2024-01/ABC12345/ABC12345.html",
      "pdf_url": "/files/2024-01/ABC12345/ABC12345.pdf"
    }
  ],
  "total": 1
}
```

### 4. Offerte Verwijderen

**DELETE** `/quote/{quote_id}`

Verwijdert een offerte en alle bijbehorende bestanden.

**Response:**
```json
{
  "success": true,
  "message": "Offerte ABC12345 succesvol verwijderd"
}
```

## 🎨 Template Customisatie

### HTML Template

De `templates/quote.html` template kan aangepast worden voor:

- **Bedrijfslogo en styling**
- **Kleurthema's**
- **Layout aanpassingen**
- **Extra secties**

### CSS Styling

De template gebruikt moderne CSS met:

- **Responsive design**
- **Print-optimale styling**
- **Professionele kleuren**
- **Grid layouts**

### Template Variabelen

Beschikbare variabelen in de template:

- `{{ lead.* }}` - Alle klantgegevens
- `{{ prediction.* }}` - Voorspelling resultaten
- `{{ pricing.* }}` - Prijsberekening
- `{{ quote_id }}` - Unieke offerte ID
- `{{ current_date }}` - Huidige datum
- `{{ validity_date }}` - Geldigheidsdatum

## 🔄 Workflow

### 1. Data Invoer
- Lead gegevens (klant, oppervlakte)
- Prediction resultaten (substraat, issues)
- Pricing berekening (automatisch)

### 2. Verwerking
- Template rendering met Jinja2
- PDF generatie via WeasyPrint
- Bestandsopslag in gestructureerde directories

### 3. Output
- HTML bestand voor web weergave
- PDF bestand voor print/opslag
- Public URLs voor toegang

### 4. Opslag
```
data/offers/
├── 2024-01/
│   ├── ABC12345/
│   │   ├── ABC12345.html
│   │   └── ABC12345.pdf
│   └── DEF67890/
│       ├── DEF67890.html
│       └── DEF67890.pdf
└── 2024-02/
    └── ...
```

## 🧪 Testen

### Test Script

Gebruik het meegeleverde test script:

```bash
python test_quote.py
```

Dit script test:
- Server connectiviteit
- Offerte generatie
- Bestand toegang
- API endpoints
- PDF download

### Handmatige Test

```bash
# Start de server
uvicorn app.main:app --reload

# Test met curl
curl -X POST "http://localhost:8000/quote/render" \
  -H "Content-Type: application/json" \
  -d @test_data.json
```

## 🚨 Troubleshooting

### WeasyPrint Problemen

**Windows:**
```bash
# Installeer via conda
conda install -c conda-forge weasyprint

# Of gebruik pre-compiled wheels
pip install --only-binary=all weasyprint
```

**Linux:**
```bash
# Installeer system dependencies
sudo apt-get install build-essential python3-dev python3-pip python3-setuptools python3-wheel python3-cffi libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info
```

**macOS:**
```bash
# Installeer via Homebrew
brew install cairo pango gdk-pixbuf libffi
```

### Template Errors

- Controleer Jinja2 syntax
- Valideer template variabelen
- Check bestandsrechten

### PDF Generatie

- Controleer WeasyPrint installatie
- Valideer HTML output
- Check diskruimte

## 📈 Uitbreidingen

### Mogelijke Verbeteringen

1. **Email integratie** - Automatische verzending
2. **CRM integratie** - Koppeling met klantgegevens
3. **Template variaties** - Verschillende stijlen
4. **Batch verwerking** - Meerdere offertes tegelijk
5. **Versioning** - Offerte geschiedenis
6. **Approval workflow** - Goedkeuringsproces

### Custom Integraties

```python
# Email verzending
from app.services.email_service import EmailService

email_service = EmailService()
email_service.send_quote(quote_result, customer_email)

# CRM update
from app.services.crm_service import CRMService

crm_service = CRMService()
crm_service.update_lead_status(lead_id, "quote_sent")
```

## 📚 Referenties

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Jinja2 Templates](https://jinja.palletsprojects.com/)
- [WeasyPrint Documentation](https://weasyprint.readthedocs.io/)
- [Pydantic Models](https://pydantic-docs.helpmanual.io/)

## 🤝 Bijdragen

Voor vragen of verbeteringen, neem contact op met het LevelAI team.

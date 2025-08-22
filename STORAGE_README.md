# Storage Adapter Documentation

## Overzicht

De Storage Adapter biedt een uniforme interface voor bestandsopslag in de LevelAI SaaS applicatie. Het ondersteunt zowel lokale bestandsopslag als Amazon S3, met de mogelijkheid om eenvoudig tussen backends te wisselen via environment variabelen.

## Architectuur

### Storage Interface

De `Storage` abstracte klasse definieert de standaard interface:

```python
class Storage(ABC):
    @abstractmethod
    def save_bytes(self, tenant_id: str, key: str, data: bytes) -> str
    @abstractmethod
    def public_url(self, tenant_id: str, key: str) -> str
    @abstractmethod
    def exists(self, tenant_id: str, key: str) -> bool
    @abstractmethod
    def delete(self, tenant_id: str, key: str) -> bool
```

### Implementaties

#### LocalStorage
- **Doel**: Lokale bestandsopslag voor development en testing
- **Pad structuur**: `{base_path}/{tenant_id}/{key}`
- **URLs**: Relatieve paden (`/files/{tenant_id}/{key}`)

#### S3Storage
- **Doel**: Cloud-gebaseerde bestandsopslag voor productie
- **S3 structuur**: `{tenant_id}/{key}` in de opgegeven bucket
- **URLs**: Publieke S3 URLs (`https://{bucket}.s3.{region}.amazonaws.com/{tenant_id}/{key}`)

## Configuratie

### Environment Variabelen

```bash
# Storage backend keuze
STORAGE_BACKEND=local  # of 's3'

# Lokale storage configuratie
LOCAL_STORAGE_PATH=data

# S3 configuratie (alleen nodig bij STORAGE_BACKEND=s3)
S3_BUCKET=your-bucket-name
S3_REGION=eu-west-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

### Factory Pattern

```python
from app.services.storage import get_storage

# Automatisch de juiste storage backend kiezen
storage = get_storage()

# Of expliciet een specifieke implementatie
from app.services.storage import LocalStorage, S3Storage
storage = LocalStorage(base_path="custom/path")
storage = S3Storage(bucket="my-bucket", region="us-east-1")
```

## Gebruik

### Basis Operaties

```python
# Bestand opslaan
key = storage.save_bytes("tenant1", "documents/quote.pdf", pdf_bytes)

# Publieke URL genereren
url = storage.public_url("tenant1", "documents/quote.pdf")

# Bestand bestaan controleren
exists = storage.exists("tenant1", "documents/quote.pdf")

# Bestand verwijderen
deleted = storage.delete("tenant1", "documents/quote.pdf")
```

### Integratie met QuoteRenderer

De `QuoteRenderer` gebruikt nu automatisch de geconfigureerde storage backend:

```python
from app.services.quote_renderer import QuoteRenderer

# Automatisch storage backend gebruiken
renderer = QuoteRenderer()

# Of expliciet storage specificeren
from app.services.storage import LocalStorage
storage = LocalStorage(base_path="custom/offers")
renderer = QuoteRenderer(storage=storage)

# Render quote (gebruikt automatisch de storage adapter)
result = renderer.render_quote(lead, prediction, pricing, tenant_settings)
print(f"PDF URL: {result['public_url']}")
```

## Tenant Isolation

Alle storage operaties zijn tenant-geïsoleerd:

- **Lokale opslag**: `data/tenant1/offers/...` vs `data/tenant2/offers/...`
- **S3 opslag**: `tenant1/offers/...` vs `tenant2/offers/...`

## Bestandsstructuur

### Offers Directory

```
offers/
├── 2024-01/
│   ├── QUOTE001/
│   │   ├── QUOTE001.html
│   │   └── QUOTE001.pdf
│   └── QUOTE002/
│       ├── QUOTE002.html
│       └── QUOTE002.pdf
└── 2024-02/
    └── QUOTE003/
        ├── QUOTE003.html
        └── QUOTE003.pdf
```

### Uploads Directory

```
uploads/
├── tenant1/
│   ├── images/
│   └── documents/
└── tenant2/
    ├── images/
    └── documents/
```

## Migratie van Oude Code

### Voor QuoteRenderer

**Oud (directe bestandspaden):**
```python
# Oude code
html_path = quote_dir / f"{quote_id}.html"
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html_content)

pdf_path = quote_dir / f"{quote_id}.pdf"
self._generate_pdf(html_content, pdf_path, tenant_settings)
```

**Nieuw (storage adapter):**
```python
# Nieuwe code
html_key = f"offers/{year_month}/{quote_id}/{quote_id}.html"
pdf_key = f"offers/{year_month}/{quote_id}/{quote_id}.pdf"

html_bytes = html_content.encode('utf-8')
self.storage.save_bytes(tenant_settings.tenant_id, html_key, html_bytes)

pdf_content = self._generate_pdf_bytes(html_content, tenant_settings)
self.storage.save_bytes(tenant_settings.tenant_id, pdf_key, pdf_content)
```

## Testing

### Lokale Tests

```bash
# Test storage functionaliteit
python test_storage.py

# Test met lokale storage
STORAGE_BACKEND=local python test_storage.py
```

### S3 Tests

```bash
# Test met S3 storage (vereist AWS credentials)
STORAGE_BACKEND=s3 S3_BUCKET=test-bucket python test_storage.py
```

## Best Practices

1. **Gebruik altijd de storage adapter** in plaats van directe bestandsoperaties
2. **Controleer bestandsexistentie** voordat je operaties uitvoert
3. **Gebruik betekenisvolle keys** die de bestandsstructuur weerspiegelen
4. **Implementeer error handling** voor storage operaties
5. **Test beide backends** tijdens development

## Troubleshooting

### Veelvoorkomende Problemen

1. **S3 toegang geweigerd**
   - Controleer AWS credentials
   - Controleer bucket permissions
   - Controleer IAM policies

2. **Lokale directory niet toegankelijk**
   - Controleer bestandsrechten
   - Controleer LOCAL_STORAGE_PATH

3. **Storage backend niet gevonden**
   - Controleer STORAGE_BACKEND waarde
   - Controleer environment variabelen

### Debugging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Storage operaties loggen
storage = get_storage()
storage.save_bytes("test", "debug.txt", b"test")
```

## Toekomstige Uitbreidingen

- **Signed URLs** voor S3 (tijdelijke toegang)
- **CDN integratie** voor betere performance
- **Backup en replicatie** strategieën
- **Compressie** van bestanden
- **Metadata** ondersteuning
- **Versioning** van bestanden

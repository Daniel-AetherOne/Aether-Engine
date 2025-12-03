# LevelAI SaaS Platform

LevelAI is een AI-gedreven SaaS-platform dat intake, voorspellingslogica, prijsbepaling en offertegeneratie automatiseert voor de bouw- en afbouwsector.  
Het systeem koppelt intake-gegevens, bestandsuploads en prijsregels aan HTML/PDF-offertes en CRM-integraties.

---

## Architectuur en Workflow

Pipeline:  
**Intake (web/WhatsApp)** → **Predict (vision placeholder)** → **Price Engine** → **Quote Generator (HTML/PDF)** → **CRM Integration**

Het platform is modulair opgebouwd met aparte modules voor intake, uploads, prijsbepaling, observability en achtergrondverwerking.

---

## Belangrijkste Features

- **Intake Management** – Webformulier met uploadondersteuning  
- **Dynamic Pricing** – Regelgebaseerde prijsengine met JSON-configuraties  
- **Quote Generation** – HTML- en PDF-offertes via Jinja2 + WeasyPrint  
- **CRM Integration** – HubSpot en andere CRM-koppelingen  
- **AI Prediction (placeholder)** – Vision-worker voor toekomstige beeldanalyse  
- **Async Processing** – Voorbereid voor achtergrondtaken  
- **Observability** – Prometheus/Grafana monitoring en structured logging

---

## Technische Stack

- **Backend:** FastAPI (Python 3.11+)  
- **Database:** PostgreSQL 15+  
- **Cache/Queue:** Redis 7+  
- **Storage:** AWS S3  
- **Infra:** Docker + Compose  
- **OS:** Windows, macOS, Linux

---

## Lokale Ontwikkelomgeving

In productie draait LevelAI als SaaS.  
De volgende stappen zijn bedoeld voor lokale ontwikkeling of testen.

### Setup

```bash
git clone https://github.com/Daniel-AetherOne/LevelAI_SaaS.git
cd LevelAI_SaaS
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # macOS/Linux
pip install -e ".[dev]"
copy env.example .env  # Voeg eigen variabelen toe
docker-compose up -d postgres redis

# LevelAI SaaS Platform

Een AI-aangedreven SaaS platform voor intake, voorspelling, prijsbepaling en CRM-integratie.

## 🎯 Doel

Pipeline: intake (web/WhatsApp) → predict (vision placeholder) → price → quote (HTML/PDF) → CRM push.

## 🚀 Features

- **Intake Management**: Web en WhatsApp integratie
- **AI Prediction**: Vision AI placeholder voor toekomstige implementatie
- **Dynamic Pricing**: Regelgebaseerde prijsbepaling
- **Quote Generation**: HTML en PDF offerte generatie
- **CRM Integration**: Push naar externe CRM systemen
- **Async Processing**: Celery placeholder voor achtergrond taken

## 🛠️ Technische Vereisten

- **Python**: 3.11+
- **Database**: PostgreSQL 15+
- **Cache**: Redis 7+
- **OS**: Windows, macOS, Linux

## 📦 Installatie

### 1. Clone Repository
```bash
git clone <repository-url>
cd LevelAI_SaaS
```

### 2. Maak Virtual Environment
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 3. Installeer Dependencies
```bash
pip install -e .
# Of voor development
pip install -e ".[dev]"
```

### 4. Environment Setup
```bash
# Kopieer environment template
copy env.example .env
# Bewerk .env met je eigen waarden
```

### 5. Database Setup
```bash
# Start PostgreSQL en Redis met Docker
docker-compose up -d postgres redis

# Of installeer lokaal:
# - PostgreSQL 15+
# - Redis 7+
```

## 🏃‍♂️ Uitvoeren

### Development Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Met Python Script
```bash
python -m app.main
```

### Met Uvicorn Direct
```bash
uvicorn app.main:app --reload
```

## 🌐 API Endpoints

- `GET /` - Root endpoint met applicatie info
- `GET /health` - Health check voor monitoring
- `GET /docs` - Auto-generated API documentatie (Swagger UI)

## 📁 Project Structuur

```
LevelAI_SaaS/
├── app/                    # Hoofdapplicatie
│   ├── main.py           # FastAPI app entry point
│   ├── routers/          # API route handlers
│   ├── services/         # Business logic
│   ├── models/           # Data models
│   ├── tasks/            # Celery tasks (placeholder)
│   ├── templates/        # Jinja2 templates
│   └── static/           # Static bestanden
├── rules/                # Prijsregels en configuratie
├── migrations/           # Database migraties
├── data/                 # Uploads en offers
├── pyproject.toml        # Project configuratie
├── docker-compose.yml    # Docker services
└── README.md            # Deze documentatie
```

## 🔧 Development

### Code Formatting
```bash
# Black formatting
black .

# Import sorting
isort .

# Linting
flake8 .

# Type checking
mypy .
```

### Testing
```bash
pytest
```

### Database Migrations
```bash
# Eerste setup
alembic init migrations

# Nieuwe migratie
alembic revision --autogenerate -m "Description"

# Migratie uitvoeren
alembic upgrade head
```

## 🐳 Docker

### Start Services
```bash
docker-compose up -d
```

### Stop Services
```bash
docker-compose down
```

### View Logs
```bash
docker-compose logs -f postgres
docker-compose logs -f redis
```

## 🔐 Environment Variables

Belangrijke environment variables in `.env`:

- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `SECRET_KEY`: Applicatie secret key
- `ENV`: Environment (development/production)

## 📚 Dependencies

### Core Dependencies
- `fastapi`: Web framework
- `uvicorn`: ASGI server
- `jinja2`: Template engine
- `weasyprint`: PDF generation
- `sqlmodel`: Database ORM
- `alembic`: Database migrations
- `python-multipart`: File uploads
- `python-dotenv`: Environment management

### Development Dependencies
- `pytest`: Testing framework
- `black`: Code formatter
- `isort`: Import sorter
- `flake8`: Linter
- `mypy`: Type checker

## 🚧 Toekomstige Features

- [ ] WhatsApp API integratie
- [ ] Vision AI implementatie
- [ ] Celery task queue
- [ ] CRM API integraties
- [ ] User authentication
- [ ] Admin dashboard
- [ ] Analytics en reporting

## 🤝 Bijdragen

1. Fork het project
2. Maak een feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit je wijzigingen (`git commit -m 'Add some AmazingFeature'`)
4. Push naar de branch (`git push origin feature/AmazingFeature`)
5. Open een Pull Request

## 📄 Licentie

Dit project is gelicenseerd onder de MIT License - zie het [LICENSE](LICENSE) bestand voor details.

## 📞 Contact

- **Email**: info@levelai.nl
- **Website**: https://levelai.nl
- **Documentatie**: [API Docs](http://localhost:8000/docs)

## 🙏 Dankwoord

Bedankt voor het gebruiken van LevelAI SaaS! 🚀





# LevelAI SaaS - Logging, Metrics & Rate Limiting

Deze documentatie beschrijft de implementatie van logging, metrics en rate limiting in de LevelAI SaaS applicatie.

## Overzicht

De applicatie is uitgebreid met:
- **Loguru logging** met context-aware logging (tenant_id, lead_id, quote_id)
- **Prometheus metrics** voor monitoring van performance en business metrics
- **Rate limiting** per tenant met Redis backend
- **Middleware** voor automatische logging en metrics collection

## Installatie

### Dependencies

Voeg de volgende packages toe aan je requirements:

```bash
pip install -r requirements_celery.txt
```

Of handmatig:

```bash
pip install loguru>=0.7.0 prometheus-client>=0.17.0 fastapi-limiter>=0.1.5 slowapi>=0.1.8
```

### Redis Setup

Zorg dat Redis draait voor rate limiting:

```bash
# Docker
docker run -d -p 6379:6379 redis:alpine

# Of start de bestaande docker-compose
docker-compose -f docker-compose.redis.yml up -d
```

## Configuratie

### Environment Variables

Maak een `.env` bestand aan:

```env
# Environment
ENVIRONMENT=development

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Logging
LOG_LEVEL=INFO
LOG_DIR=logs

# Rate Limiting
RATE_LIMIT_QUOTE_CREATE=60
RATE_LIMIT_VISION_PROCESSING=30
RATE_LIMIT_PREDICTION=100
```

### Configuratie Bestanden

De applicatie gebruikt `app/config.py` voor centrale configuratie. Alle instellingen kunnen via environment variables worden overschreven.

## Functionaliteit

### 1. Logging (Loguru)

#### Context-Aware Logging

Elke logregel bevat automatisch:
- `tenant_id`: Huidige tenant context
- `lead_id`: Huidige lead context (indien beschikbaar)
- `quote_id`: Huidige quote context (indien beschikbaar)

#### Gebruik

```python
from app.logging_config import get_logger, set_context, LoggingContext

# Automatische context via middleware
logger = get_logger(__name__)
logger.info("Request verwerkt")

# Handmatige context setting
set_context(tenant_id="tenant1", lead_id="lead123")
logger.info("Lead verwerkt")

# Context manager voor tijdelijke context
with LoggingContext(tenant_id="tenant1", lead_id="lead123"):
    logger.info("Tijdelijke context")
```

#### Log Output

```
2024-01-01 12:00:00 | INFO     | app.routers.quote:create_quote:45 | tenant_id=tenant1 | lead_id=lead123 | quote_id=None | Quote creatie gestart
```

#### Log Bestanden

- `logs/app.log`: Alle logs (DEBUG level)
- `logs/errors.log`: Alleen errors
- Console output met kleuren

### 2. Metrics (Prometheus)

#### Beschikbare Metrics

**Request Metrics:**
- `http_requests_total`: Totaal aantal HTTP requests
- `http_request_duration_seconds`: Request latency

**Job Metrics:**
- `celery_jobs_total`: Totaal aantal Celery jobs
- `celery_job_duration_seconds`: Job latency

**Vision Metrics:**
- `vision_confidence_score`: Model confidence score
- `vision_processing_duration_seconds`: Processing time

**Business Metrics:**
- `quotes_created_total`: Aantal quotes aangemaakt
- `leads_processed_total`: Aantal leads verwerkt
- `active_users`: Aantal actieve gebruikers

#### Metrics Endpoints

- `/metrics`: Prometheus format
- `/metrics/summary`: JSON samenvatting
- `/metrics/dashboard`: HTML dashboard
- `/metrics/rate-limits`: Rate limit informatie

#### Metrics Registratie

```python
from app.metrics import record_quote_metrics, record_vision_metrics

# Quote metrics
record_quote_metrics(tenant_id="tenant1", status="created")

# Vision metrics
record_vision_metrics(
    model_type="pytorch", 
    tenant_id="tenant1", 
    confidence=0.85, 
    processing_time=2.5
)
```

### 3. Rate Limiting

#### Per-Tenant Limits

- **Quote Creation**: 60 requests/minute
- **Vision Processing**: 30 requests/minute  
- **Prediction**: 100 requests/minute
- **Global**: 1000 requests/minute per IP

#### Implementatie

Rate limiting wordt automatisch toegepast via decorators:

```python
from app.rate_limiting import quote_create_rate_limit

@router.post("/create")
@quote_create_rate_limit()
async def create_quote(request: QuoteCreateRequest):
    # Endpoint is automatisch rate limited
    pass
```

#### Rate Limit Headers

Response headers bevatten rate limit informatie:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 30
```

#### Rate Limit Endpoints

- `GET /metrics/rate-limits`: Overzicht van alle limits
- `GET /metrics/rate-limits/{tenant_id}`: Tenant-specifieke info
- `POST /metrics/rate-limits/reset`: Reset alle limits
- `POST /metrics/rate-limits/{tenant_id}/reset`: Reset tenant limits

### 4. Middleware

#### Automatische Functionaliteit

De middleware zorgt voor:
- Context-aware logging voor alle requests
- Request metrics collection
- Rate limit headers
- Error logging en monitoring

#### Middleware Volgorde

1. **LoggingMiddleware**: Context setting en request logging
2. **RateLimitMiddleware**: Rate limit headers
3. **MetricsMiddleware**: Request metrics (ASGI level)
4. **CORSMiddleware**: CORS handling

## Monitoring & Dashboard

### Prometheus Dashboard

Gebruik het HTML dashboard op `/metrics/dashboard` voor real-time monitoring:

- Request counts en latency
- Job processing metrics
- Business metrics
- Rate limit status
- Auto-refresh elke 30 seconden

### Grafana Integration

Voor productie monitoring, integreer met Grafana:

```yaml
# grafana/datasources/prometheus.yml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    url: http://localhost:8000/metrics
    access: proxy
```

### Health Checks

- `/health`: Basis health check
- `/health/detailed`: Uitgebreide health check met metrics

## Development

### Local Testing

```bash
# Start applicatie
python -m uvicorn app.main:app --reload

# Test rate limiting
curl -X POST "http://localhost:8000/quote/create" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "test", "lead_id": "test123", ...}'

# Bekijk metrics
curl http://localhost:8000/metrics/summary

# Bekijk dashboard
open http://localhost:8000/metrics/dashboard
```

### Testing Rate Limits

```bash
# Test rate limiting (60 requests per minute)
for i in {1..65}; do
  curl -X POST "http://localhost:8000/quote/create" \
    -H "Content-Type: application/json" \
    -d '{"tenant_id": "test", "lead_id": "test123", ...}'
  echo "Request $i"
done

# Na 60 requests krijg je 429 Too Many Requests
```

### Log Analysis

```bash
# Bekijk real-time logs
tail -f logs/app.log

# Filter op tenant
grep "tenant_id=tenant1" logs/app.log

# Filter op errors
tail -f logs/errors.log
```

## Production Deployment

### Environment Variables

```env
ENVIRONMENT=production
LOG_LEVEL=WARNING
REDIS_HOST=redis.production.com
REDIS_PASSWORD=secure_password
```

### Monitoring Stack

1. **Prometheus**: Metrics collection
2. **Grafana**: Dashboards en alerting
3. **Redis**: Rate limiting en caching
4. **ELK Stack**: Log aggregation (optioneel)

### Scaling

- **Horizontal**: Meerdere app instances achter load balancer
- **Vertical**: Meer CPU/memory voor hogere throughput
- **Redis Cluster**: Voor high-availability rate limiting

## Troubleshooting

### Veelvoorkomende Problemen

1. **Redis Connection Failed**
   - Check of Redis draait
   - Verifieer connection settings

2. **Rate Limiting Werkt Niet**
   - Check Redis connectivity
   - Verifieer tenant_id in requests

3. **Metrics Tonen 0**
   - Check of Prometheus client correct is geïnstalleerd
   - Verifieer metrics endpoints

4. **Logs Tonen Geen Context**
   - Check middleware volgorde
   - Verifieer context setting

### Debug Mode

```env
LOG_LEVEL=DEBUG
ENVIRONMENT=development
```

### Health Check

```bash
curl http://localhost:8000/health/detailed
```

## Best Practices

### Logging

- Gebruik altijd de context-aware logger
- Log belangrijke business events
- Vermijd logging van gevoelige data
- Gebruik consistente log levels

### Metrics

- Registreer metrics voor alle belangrijke operaties
- Gebruik betekenisvolle labels
- Vermijd te veel cardinaliteit
- Monitor trends over tijd

### Rate Limiting

- Stel realistische limits in
- Monitor rate limit violations
- Implementeer graceful degradation
- Overweeg burst allowances

## Conclusie

De implementatie biedt een complete monitoring en observability oplossing voor de LevelAI SaaS applicatie. Alle componenten werken samen om inzicht te geven in performance, gebruik en gezondheid van het systeem.

Voor vragen of problemen, raadpleeg de code comments of neem contact op met het development team.

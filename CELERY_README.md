# LevelAI SaaS - Celery Implementation

Deze implementatie verplaatst zware taken naar Celery workers om de API responsiviteit te verbeteren.

## Architectuur

### Celery App (`app/celery_app.py`)
- Redis broker en backend configuratie
- Job status tracking systeem
- Celery configuratie voor optimalisatie

### Celery Tasks (`app/celery_tasks.py`)
- `vision_predict`: AI vision predictie
- `compute_price`: Prijsberekening
- `generate_pdf`: PDF generatie
- `crm_push`: HubSpot CRM integratie

### Workflow
```
/quote/create → enqueue vision_predict → compute_price → generate_pdf → crm_push
     ↓
  201 status_id
```

## Setup

### 1. Dependencies installeren
```bash
pip install -r requirements_celery.txt
```

### 2. Redis starten
```bash
docker-compose -f docker-compose.redis.yml up -d
```

### 3. Celery worker starten
```bash
python start_celery_worker.py
```

### 4. FastAPI applicatie starten
```bash
uvicorn app.main:app --reload
```

## API Endpoints

### POST /quote/create
- Start asynchrone quote creatie
- Retourneert onmiddellijk `201` met `status_id`
- Alle zware taken worden naar Celery workers gestuurd

### GET /jobs/{id}
- Haalt job status op
- Retourneert huidige stap en voortgang
- Bij voltooiing: `public_url` voor de gegenereerde offerte

## Job Status Tracking

Jobs doorlopen de volgende statussen:
1. `pending`: Job aangemaakt, wacht op verwerking
2. `processing`: Taak wordt uitgevoerd
3. `completed`: Taak succesvol voltooid
4. `failed`: Taak gefaald met foutmelding

## Monitoring

### Flower Dashboard
- URL: http://localhost:5555
- Monitor Celery workers en taken
- Bekijk queue status en performance

### Logs
- Celery worker logs tonen taak voortgang
- FastAPI logs tonen API requests en responses

## Performance

### Acceptatie Criteria
- ✅ API blijft snel bij 5 gelijktijdige aanvragen
- ✅ Response tijd onder 200ms
- ✅ Jobs worden afgehandeld door workers

### Optimalisaties
- Worker concurrency: 4 processen
- Task timeouts: 30 minuten
- Prefetch multiplier: 1 (voor betere load balancing)

## Testing

### Test Script
```bash
python test_celery.py
```

Test scenario's:
1. Enkele quote creatie
2. Job status polling
3. 5 gelijktijdige aanvragen

### Load Testing
```bash
# Test met Apache Bench (optioneel)
ab -n 100 -c 5 -H "X-Tenant-ID: demo" -p test_data.json http://localhost:8000/quote/create
```

## Productie Deployment

### Environment Variables
```bash
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
```

### Scaling
- Start meerdere Celery workers
- Gebruik Redis cluster voor hoge beschikbaarheid
- Monitor worker health en restart bij problemen

### Health Checks
- Redis connectivity
- Celery worker status
- Queue depth monitoring

## Troubleshooting

### Veelvoorkomende Problemen

1. **Redis Connection Error**
   - Controleer of Redis draait
   - Verifieer REDIS_URL configuratie

2. **Worker Start Fout**
   - Controleer Python path
   - Verifieer alle dependencies

3. **Tasks Blijven Hangen**
   - Check worker logs
   - Verifieer task timeouts
   - Restart workers indien nodig

### Debug Mode
```bash
# Start worker met debug logging
celery -A app.celery_app worker --loglevel=debug
```

## Volgende Stappen

1. **Celery Chains**: Implementeer echte Celery chains voor betere workflow
2. **Retry Logic**: Voeg retry mechanismen toe voor failed tasks
3. **Priority Queues**: Implementeer prioriteit voor urgente taken
4. **Distributed Workers**: Schaal naar meerdere machines
5. **Monitoring**: Integreer met Prometheus/Grafana

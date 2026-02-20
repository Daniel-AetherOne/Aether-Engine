# Cloud Run – noodzakelijke environment variables (LevelAI)

Deze vars moeten gezet worden in Cloud Run. Alle andere mogen (voor nu) wegblijven.

## Core app

- `APP_ENV=production`
- `PUBLIC_BASE_URL=https://<jouw-domain>`
- `SECRET_KEY=<sterke-random-secret>`

## Storage / S3

- `AWS_REGION=eu-west-1`
- `S3_BUCKET=levelai-prod-files`
- `CLOUDFRONT_DOMAIN=https://d1bjdnx9r99951.cloudfront.net`

## Database & Redis

- `DATABASE_URL=postgresql://<user>:<pass>@<host>:5432/levelai_db`
- `REDIS_URL=redis://<redis-host>:6379/0`

## E-mail (optioneel)

Alleen nodig als e-mail aan staat:

- `SMTP_HOST=<smtp-host>`
- `SMTP_USER=<smtp-user>`
- `SMTP_PASSWORD=<smtp-password>`

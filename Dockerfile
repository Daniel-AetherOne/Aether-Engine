FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ /app/app
COPY migrations/ /app/migrations
COPY alembic.ini /app/alembic.ini
COPY gunicorn.conf.py /app/gunicorn.conf.py

EXPOSE 8080
ENV PORT=8080

CMD ["gunicorn","-k","uvicorn.workers.UvicornWorker","-c","/app/gunicorn.conf.py","app.main:app"]
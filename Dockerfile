FROM python:3.11-slim

# Snellere/kleinere installs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Eventuele systeemlibs (laat staan als je Pillow/vision gebruikt)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Dependencies eerst (beter cachegebruik)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) Code + gunicorn config
COPY app/ /app/app
COPY gunicorn.conf.py /app/gunicorn.conf.py

# Cloud Run gebruikt $PORT; gunicorn.conf.py bindt daaraan
EXPOSE 8080

# Start FastAPI via Gunicorn + Uvicorn worker
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-c", "gunicorn.conf.py", "app.main:app"]

FROM python:3.11-slim

# Snellere/zuinigere Python + pip
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 1) Alleen requirements kopiëren en installeren
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
      libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && python -c "import email_validator; print('email_validator OK')"

# 2) Dan pas de rest van de code
COPY . .

# Cloud Run luistert op $PORT (expose is informatief)
EXPOSE 8080

# Gunicorn pakt config automatisch op uit /app
ENV GUNICORN_CMD_ARGS="--config gunicorn_conf.py"

# BLAS/NumPy threads laag houden (minder RAM/CPU)
ENV OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1

# Enige CMD
CMD ["gunicorn", "app.main:app"]

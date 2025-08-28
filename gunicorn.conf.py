# gunicorn_conf.py
import os

bind = f"0.0.0.0:{os.getenv('PORT', '8080')}"
workers = int(os.getenv("WEB_CONCURRENCY", "2"))  # schaalbaar via env
threads = int(os.getenv("WEB_THREADS", "4"))      # idem
worker_class = "uvicorn.workers.UvicornWorker"
preload_app = False
timeout = 120
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
accesslog = "-"
errorlog = "-"
loglevel = "info"

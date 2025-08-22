#!/usr/bin/env python3
"""
Start Celery worker voor LevelAI SaaS
"""
import os
import sys
from pathlib import Path

# Voeg project root toe aan Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.celery_app import celery_app

if __name__ == "__main__":
    # Start Celery worker
    celery_app.worker_main([
        "worker",
        "--loglevel=info",
        "--concurrency=4",  # Aantal worker processen
        "--hostname=levelai-worker@%h",  # Unieke worker naam
        "--queues=default",  # Queue naam
        "--without-gossip",  # Schakel gossip uit voor single worker
        "--without-mingle",  # Schakel mingle uit voor single worker
        "--without-heartbeat"  # Schakel heartbeat uit voor single worker
    ])

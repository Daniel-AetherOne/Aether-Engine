#!/usr/bin/env python3
"""
Start script voor LevelAI SaaS met Celery
"""
import subprocess
import time
import sys
import os
from pathlib import Path

def run_command(command, description, background=False):
    """Voer commando uit"""
    print(f"🚀 {description}...")
    
    if background:
        # Start in background
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print(f"✅ {description} gestart in background (PID: {process.pid})")
        return process
    else:
        # Start en wacht
        try:
            result = subprocess.run(command, shell=True, check=True)
            print(f"✅ {description} voltooid")
            return result
        except subprocess.CalledProcessError as e:
            print(f"❌ {description} gefaald: {e}")
            return None

def check_redis():
    """Controleer of Redis draait"""
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        print("✅ Redis is beschikbaar")
        return True
    except Exception as e:
        print(f"❌ Redis niet beschikbaar: {e}")
        return False

def main():
    """Start alle services"""
    print("🚀 LevelAI SaaS - Starting all services...")
    print("=" * 50)
    
    # Controleer of we in de juiste directory zijn
    if not Path("app").exists():
        print("❌ Fout: Start dit script vanuit de project root directory")
        sys.exit(1)
    
    # Stap 1: Start Redis (als Docker beschikbaar is)
    print("\n📦 Stap 1: Redis starten...")
    try:
        run_command(
            "docker-compose -f docker-compose.redis.yml up -d",
            "Redis starten met Docker Compose"
        )
        time.sleep(3)  # Wacht tot Redis opstart
    except Exception as e:
        print(f"⚠️  Docker niet beschikbaar, probeer Redis handmatig te starten: {e}")
    
    # Stap 2: Controleer Redis
    print("\n🔍 Stap 2: Redis connectiviteit controleren...")
    if not check_redis():
        print("❌ Redis is niet beschikbaar. Start Redis handmatig en probeer opnieuw.")
        print("   Commando: docker-compose -f docker-compose.redis.yml up -d")
        sys.exit(1)
    
    # Stap 3: Start Celery worker
    print("\n👷 Stap 3: Celery worker starten...")
    worker_process = run_command(
        "python start_celery_worker.py",
        "Celery worker starten",
        background=True
    )
    
    if not worker_process:
        print("❌ Celery worker kon niet worden gestart")
        sys.exit(1)
    
    # Stap 4: Start FastAPI applicatie
    print("\n🌐 Stap 4: FastAPI applicatie starten...")
    api_process = run_command(
        "uvicorn app.main:app --reload --host 0.0.0.0 --port 8000",
        "FastAPI applicatie starten",
        background=True
    )
    
    if not api_process:
        print("❌ FastAPI applicatie kon niet worden gestart")
        sys.exit(1)
    
    # Wacht even en toon status
    time.sleep(3)
    
    print("\n" + "=" * 50)
    print("🎉 Alle services zijn gestart!")
    print("\n📋 Service URLs:")
    print("   • FastAPI: http://localhost:8000")
    print("   • API Docs: http://localhost:8000/docs")
    print("   • Flower Dashboard: http://localhost:5555")
    print("\n📝 Volgende stappen:")
    print("   1. Test de API: python test_celery.py")
    print("   2. Bekijk logs in de terminal vensters")
    print("   3. Monitor taken in Flower dashboard")
    print("\n🛑 Om te stoppen: Ctrl+C in beide terminal vensters")
    print("=" * 50)
    
    try:
        # Houd script draaiend
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Services stoppen...")
        
        # Stop processes
        if worker_process:
            worker_process.terminate()
            print("✅ Celery worker gestopt")
        
        if api_process:
            api_process.terminate()
            print("✅ FastAPI applicatie gestopt")
        
        print("👋 Alle services gestopt")

if __name__ == "__main__":
    main()

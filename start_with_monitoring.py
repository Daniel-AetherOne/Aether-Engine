#!/usr/bin/env python3
"""
Start script voor LevelAI SaaS met monitoring functionaliteit
"""

import subprocess
import time
import os
import sys
from pathlib import Path

def check_dependencies():
    """Check of alle dependencies geïnstalleerd zijn"""
    print("🔍 Checking dependencies...")
    
    required_packages = [
        "loguru",
        "prometheus_client", 
        "fastapi_limiter",
        "slowapi",
        "redis"
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package} - MISSING")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n❌ Missing packages: {', '.join(missing_packages)}")
        print("Install with: pip install -r requirements_celery.txt")
        return False
    
    print("  ✅ All dependencies installed")
    return True

def start_redis():
    """Start Redis met Docker"""
    print("\n🐳 Starting Redis...")
    
    try:
        # Check if Redis is already running
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=levelai_redis", "--format", "{{.Names}}"],
            capture_output=True, text=True
        )
        
        if "levelai_redis" in result.stdout:
            print("  ✅ Redis already running")
            return True
        
        # Start Redis
        print("  Starting Redis container...")
        subprocess.run([
            "docker-compose", "-f", "docker-compose.redis.yml", "up", "-d", "redis"
        ], check=True)
        
        # Wait for Redis to be ready
        print("  Waiting for Redis to be ready...")
        time.sleep(5)
        
        print("  ✅ Redis started successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Failed to start Redis: {e}")
        return False
    except FileNotFoundError:
        print("  ❌ Docker not found. Please install Docker and Docker Compose")
        return False

def create_directories():
    """Maak benodigde directories aan"""
    print("\n📁 Creating directories...")
    
    directories = [
        "logs",
        "data/uploads",
        "data/offers"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"  ✅ {directory}")

def start_application():
    """Start de FastAPI applicatie"""
    print("\n🚀 Starting LevelAI SaaS application...")
    
    try:
        # Start the application
        print("  Starting with uvicorn...")
        print("  Application will be available at: http://localhost:8000")
        print("  Metrics dashboard: http://localhost:8000/metrics/dashboard")
        print("  Prometheus metrics: http://localhost:8000/metrics")
        print("  Redis Commander: http://localhost:8081")
        print("\n  Press Ctrl+C to stop")
        
        subprocess.run([
            sys.executable, "-m", "uvicorn", 
            "app.main:app", 
            "--host", "0.0.0.0", 
            "--port", "8000", 
            "--reload"
        ])
        
    except KeyboardInterrupt:
        print("\n\n🛑 Application stopped by user")
    except Exception as e:
        print(f"\n❌ Failed to start application: {e}")

def main():
    """Main function"""
    print("🚀 LevelAI SaaS - Starting with Monitoring")
    print("=" * 50)
    
    # Check dependencies
    if not check_dependencies():
        sys.exit(1)
    
    # Create directories
    create_directories()
    
    # Start Redis
    if not start_redis():
        print("\n⚠️  Warning: Redis not available. Rate limiting will not work.")
        print("   You can still test logging and metrics functionality.")
    
    # Start application
    start_application()

if __name__ == "__main__":
    main()

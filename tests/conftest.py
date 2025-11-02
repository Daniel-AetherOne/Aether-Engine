import os
os.environ.setdefault("DISABLE_BG", "1")  # bg worker uit tijdens tests
import asyncio
# --- DB setup for tests: create tables once, drop afterwards ---
import pytest
from app.db import Base, engine

@pytest.fixture(scope="session", autouse=True)
def _create_test_db():
    # zorg dat modellen geladen zijn, anders kent Base de tabellen niet
    from app import models  # of: from app.models import upload_status
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def anyio_backend():
    # Dwing anyio om alleen asyncio te gebruiken (geen Trio nodig)
    return "asyncio"
from fastapi.testclient import TestClient

# 👉 Pas deze import aan naar jouw app entrypoint
from app.main import app

# Dummy env zodat boto3/moto niet zeurt als jij later live test
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
def client():
    return TestClient(app)

@pytest.fixture
def auth_headers():
    # 👉 Pas aan aan jouw auth (bijv. Bearer token of X-User-Id)
    return {"Authorization": "Bearer testtoken"}

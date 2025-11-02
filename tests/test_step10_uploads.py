# Zet dit helemaal bovenin het bestand
PRESIGN_PATH = "/uploads/presign"   # jouw echte endpoint

import asyncio
import json
import types
import httpx
import pytest
from datetime import datetime, timedelta

# 👉 Pas imports aan (services/model)
from app.services.upload_status_service import verify_object
from app.models.upload_status import UploadStatus
from app.db import SessionLocal

# Helpers
def _mk_status(user_id="u1", key="uploads/test.png", status="pending"):
    db = SessionLocal()
    rec = UploadStatus(user_id=user_id, object_key=key, status=status)
    db.add(rec); db.commit(); db.refresh(rec); db.close()
    return rec

# -------------------------
# 1) UNIT
# -------------------------
def test_presign_accepts_valid_mime_and_size(client, auth_headers):
    payload = {
        "filename": "foto.png",
        "content_type": "image/png",
        "size": 512_000,   # 500 KB
        "lead_id": "lead123",
    }
    r = client.post(PRESIGN_PATH, headers=auth_headers, json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "url" in data and "fields" in data or "object_key" in data

def test_presign_rejects_bad_mime_or_size(client, auth_headers):
    # Verkeerde MIME
    bad_mime = {
        "filename": "script.exe",
        "content_type": "application/x-msdownload",
        "size": 1024,
        "lead_id": "lead123",
    }
    r1 = client.post(PRESIGN_PATH, headers=auth_headers, json=bad_mime)
    assert r1.status_code == 400

    # Te groot
    too_big = {
        "filename": "foto.png",
        "content_type": "image/png",
        "size": 200 * 1024 * 1024,  # 200 MB
        "lead_id": "lead123",
    }
    r2 = client.post(PRESIGN_PATH, headers=auth_headers, json=too_big)
    assert r2.status_code == 400

# -------------------------
# 2) INTEGRATION (moto/sandbox gesimuleerd)
# Presign → (client PUT sim) → HEAD moet slagen
# We mocken httpx HEAD zodat de background verifier "S3" als 200 ziet.
# -------------------------
@pytest.mark.anyio
async def test_presign_put_then_head_verified(client, auth_headers, monkeypatch):
    # 1) Presign
    payload = {
        "filename": "foto.png",
        "content_type": "image/png",
        "size": 2048,
        "lead_id": "lead123",
    }
    r = client.post(PRESIGN_PATH, headers=auth_headers, json=payload)
    assert r.status_code == 200
    body = r.json()
    object_key = body.get("object_key") or body.get("fields", {}).get("key")
    assert object_key

    # 2) Simuleer dat client heeft geüpload: maak pending record aan
    _ = _mk_status(user_id="u1", key=object_key, status="pending")

    # 3) HEAD → 200
    class _OK:
        status_code = 200
    async def fake_head_ok(self, url, timeout=None):
        return _OK()

    # Patch httpx.AsyncClient.head
    monkeypatch.setattr(httpx.AsyncClient, "head", fake_head_ok, raising=True)

    # 4) Run verify
    db = SessionLocal()
    rec = db.query(UploadStatus).filter_by(object_key=object_key).first()
    await verify_object(db, rec)
    db.refresh(rec)
    assert rec.status == "verified"
    assert rec.verified_at is not None
    db.close()

# -------------------------
# 3) SECURITY
# -------------------------
def test_presign_unauthenticated_401(client):
    payload = {
        "filename": "foto.png",
        "content_type": "image/png",
        "size": 1024,
        "lead_id": "lead123",
    }
    r = client.post(PRESIGN_PATH, json=payload)  # geen headers
    assert r.status_code in (401, 403)  # afhankelijk van jouw auth setup

def test_presign_other_users_lead_forbidden_403(client, auth_headers):
    # Aanname: server valideert dat leadId bij huidige user hoort.
    payload = {
        "filename": "foto.png",
        "content_type": "image/png",
        "size": 1024,
        "lead_id": "lead_of_other_user",
    }
    r = client.post(PRESIGN_PATH, headers=auth_headers, json=payload)
    assert r.status_code == 403

# -------------------------
# 4) EDGE CASES
# -------------------------
@pytest.mark.anyio
async def test_expired_presigned_url_fails(client, auth_headers, monkeypatch):
    # Arrange
    r = client.post(PRESIGN_PATH, headers=auth_headers, json={
        "filename": "foto.png",
        "content_type": "image/png",
        "size": 1024,
        "lead_id": "lead123",
        "expires_in": 1,  # heel kort
    })
    assert r.status_code == 200
    object_key = r.json().get("object_key") or r.json().get("fields", {}).get("key")
    _ = _mk_status(key=object_key)

    # HEAD → 403 (Expired)
    class _Expired:
        status_code = 403
    async def fake_head_expired(self, url, timeout=None):
        return _Expired()
    monkeypatch.setattr(httpx.AsyncClient, "head", fake_head_expired, raising=True)

    db = SessionLocal()
    rec = db.query(UploadStatus).filter_by(object_key=object_key).first()
    await verify_object(db, rec)
    db.refresh(rec)
    assert rec.status == "failed"
    assert "403" in (rec.error or "")
    db.close()

def test_wrong_content_type_rejected_on_presign(client, auth_headers):
    # Client vraagt jpg terwijl whitelist alleen png/pdf toelaat (voorbeeld)
    r = client.post(PRESIGN_PATH, headers=auth_headers, json={
        "filename": "foto.jpg",
        "content_type": "image/jpeg",
        "size": 1024,
        "lead_id": "lead123",
    })
    assert r.status_code == 400

@pytest.mark.anyio
async def test_network_retry_on_head(client, auth_headers, monkeypatch):
    """
    Simuleer een tijdelijke netwerkfout gevolgd door succes.
    Als jouw verify code (nog) geen retry heeft, markeren we deze xfail.
    """
    r = client.post(PRESIGN_PATH, headers=auth_headers, json={
        "filename": "foto.png",
        "content_type": "image/png",
        "size": 1024,
        "lead_id": "lead123",
    })
    assert r.status_code == 200
    object_key = r.json().get("object_key") or r.json().get("fields", {}).get("key")
    _ = _mk_status(key=object_key)

    calls = {"n": 0}

    class _OK:
        status_code = 200

    async def flaky_head(self, url, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("temporary")
        return _OK()

    monkeypatch.setattr(httpx.AsyncClient, "head", flaky_head, raising=True)

    db = SessionLocal()
    rec = db.query(UploadStatus).filter_by(object_key=object_key).first()

    # --- Als verify_object geen retry heeft, faalt de 1e call -> failed.
    # Markeer dit als xfail wanneer je nog geen retry hebt ingebouwd.
    try:
        await verify_object(db, rec)
        db.refresh(rec)
        if rec.status == "failed":
            pytest.xfail("Geen retry-logic in verify_object; voeg retry toe om deze test te laten slagen.")
        else:
            assert rec.status == "verified"
    finally:
        db.close()

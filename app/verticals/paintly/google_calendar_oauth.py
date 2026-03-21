from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.core.settings import settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_token(plain_text: str) -> str:
    return _fernet().encrypt((plain_text or "").encode("utf-8")).decode("utf-8")


def decrypt_token(cipher_text: str) -> str:
    try:
        return _fernet().decrypt((cipher_text or "").encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise HTTPException(status_code=500, detail="Stored integration token is invalid.") from exc


def _state_signature(payload_json: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload_json.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _build_redirect_uri() -> str:
    custom = (settings.GOOGLE_OAUTH_REDIRECT_URI or "").strip()
    if custom:
        return custom
    return f"{settings.APP_PUBLIC_BASE_URL.rstrip('/')}/integrations/google-calendar/callback"


def build_google_auth_url(tenant_id: str) -> str:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured.")

    payload = {"tenant_id": tenant_id, "ts": int(time.time())}
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    state_blob = {"p": payload, "sig": _state_signature(payload_json)}
    state = base64.urlsafe_b64encode(
        json.dumps(state_blob, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("utf-8")

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": _build_redirect_uri(),
        "response_type": "code",
        "scope": settings.GOOGLE_CALENDAR_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


def validate_oauth_state(state: str, *, max_age_seconds: int = 900) -> str:
    try:
        raw = base64.urlsafe_b64decode(state.encode("utf-8")).decode("utf-8")
        state_blob = json.loads(raw)
        payload = state_blob["p"]
        signature = state_blob["sig"]
        payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid OAuth state.") from exc

    expected = _state_signature(payload_json)
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=400, detail="Invalid OAuth state signature.")

    ts = int(payload.get("ts", 0))
    if int(time.time()) - ts > max_age_seconds:
        raise HTTPException(status_code=400, detail="OAuth state expired.")

    tenant_id = str(payload.get("tenant_id") or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="OAuth state missing tenant.")
    return tenant_id


def exchange_code_for_tokens(code: str) -> dict[str, Any]:
    data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": _build_redirect_uri(),
    }
    with httpx.Client(timeout=15.0) as client:
        response = client.post(GOOGLE_TOKEN_URL, data=data)
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail="Failed to exchange Google OAuth code.")
    return response.json()


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    with httpx.Client(timeout=15.0) as client:
        response = client.post(GOOGLE_TOKEN_URL, data=data)
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail="Failed to refresh Google access token.")
    return response.json()


def token_expiry_from_response(token_payload: dict[str, Any]) -> datetime | None:
    expires_in = token_payload.get("expires_in")
    if not expires_in:
        return None
    try:
        return datetime.now(UTC) + timedelta(seconds=int(expires_in))
    except Exception:
        return None


def create_google_calendar_event(
    *,
    access_token: str,
    calendar_id: str,
    event_payload: dict[str, Any],
) -> dict[str, Any]:
    encoded_calendar = urllib.parse.quote(calendar_id or "primary", safe="")
    url = f"{GOOGLE_CALENDAR_API}/calendars/{encoded_calendar}/events"
    with httpx.Client(timeout=20.0) as client:
        response = client.post(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=event_payload,
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail="Failed to create Google Calendar event.")
    return response.json()

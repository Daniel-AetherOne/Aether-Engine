# app/services/s3_keys.py
from datetime import datetime
from pathlib import PurePosixPath
import uuid


def s3_key_join(*parts: str) -> str:
    cleaned = [str(p).strip("/ ") for p in parts if p is not None and str(p).strip("/ ")]
    return "/".join(cleaned)


def _safe_filename(filename: str) -> str:
    filename = filename.replace("..", "")
    filename = filename.replace("/", "_")
    return filename


def build_quote_key(tenant_id: str, quote_id: str) -> str:
    # quotes/{tenant_id}/{quote_id}/index.html
    return s3_key_join("quotes", tenant_id, quote_id, "index.html")


def build_quote_version_key(tenant_id: str, quote_id: str, ts: datetime) -> str:
    # quotes/{tenant_id}/{quote_id}/versions/{timestamp}.html
    ts_str = ts.strftime("%Y%m%dT%H%M%SZ")
    return s3_key_join("quotes", tenant_id, quote_id, "versions", f"{ts_str}.html")


def build_upload_key(tenant_id: str, lead_id: str, filename: str) -> str:
    # uploads/{tenant_id}/{lead_id}/{uuid}_{filename}
    sanitized = _safe_filename(filename)
    uid = uuid.uuid4().hex
    return s3_key_join("uploads", tenant_id, lead_id, f"{uid}_{sanitized}")

# app/services/storage.py
from __future__ import annotations

import logging
import mimetypes
import shutil
import stat
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import quote

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from app.core.settings import settings

logger = logging.getLogger(__name__)

# =========================
# Config / Policies
# =========================
TEMP_PREFIX = settings.S3_TEMP_PREFIX
FINAL_PREFIX = settings.S3_FINAL_PREFIX
MAX_BYTES = settings.UPLOAD_MAX_BYTES

_default_types = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
_env_types = {
    t.strip()
    for t in (settings.UPLOAD_ALLOWED_CONTENT_TYPES or "").split(",")
    if t.strip()
}
ALLOWED_CONTENT_TYPES = _default_types.union(_env_types)


# =========================
# Abstracte Storage
# =========================
class Storage(ABC):
    """Abstracte Storage interface voor bestandsopslag."""

    @abstractmethod
    def head(self, tenant_id: str, key: str) -> Dict:
        raise NotImplementedError

    @abstractmethod
    def save_bytes(
        self,
        tenant_id: str,
        key: str,
        data: bytes,
        *,
        content_type: Optional[str] = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def public_url(self, tenant_id: str, key: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def exists(self, tenant_id: str, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete(self, tenant_id: str, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def download_to_temp_path(self, tenant_id: str, key: str) -> str:
        raise NotImplementedError

    def put_text(
        self,
        tenant_id: str,
        key: str,
        text: str,
        content_type: str = "text/html; charset=utf-8",
    ) -> str:
        """
        Backend-agnostic: schrijf text via save_bytes().
        Werkt voor LocalStorage en S3Storage.
        """
        return self.save_bytes(
            tenant_id=tenant_id,
            key=key,
            data=text.encode("utf-8"),
            content_type=content_type,
        )


# =========================
# Local Storage
# =========================
class LocalStorage(Storage):
    """Lokale bestandsopslag implementatie."""

    def __init__(self, base_path: str = "data"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _full_path(self, tenant_id: str, key: str) -> Path:
        tenant_id = (tenant_id or "").strip().strip("/")
        key = (key or "").strip().lstrip("/")
        return self.base_path / tenant_id / key

    def head(self, tenant_id: str, key: str) -> Dict:
        meta = self._head_local(tenant_id, key)
        if not meta:
            raise RuntimeError("not_found")
        return {
            "size_bytes": int(meta.get("ContentLength", 0) or 0),
            "content_type": str(meta.get("ContentType") or ""),
        }

    def save_bytes(
        self,
        tenant_id: str,
        key: str,
        data: bytes,
        *,
        content_type: Optional[str] = None,
    ) -> str:
        file_path = self._full_path(tenant_id, key)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(data)
        logger.info("Local opgeslagen: %s", file_path)
        return key

    def public_url(self, tenant_id: str, key: str) -> str:
        key = (key or "").lstrip("/")
        return f"/files/{tenant_id}/{key}"

    def exists(self, tenant_id: str, key: str) -> bool:
        return self._full_path(tenant_id, key).exists()

    def delete(self, tenant_id: str, key: str) -> bool:
        try:
            p = self._full_path(tenant_id, key)
            if p.exists():
                p.unlink()
                logger.info("Local verwijderd: %s", p)
                return True
            return False
        except Exception as e:
            logger.error("Local delete error key=%s: %s", key, e)
            return False

    def download_to_temp_path(self, tenant_id: str, key: str) -> str:
        p = self._full_path(tenant_id, key)
        if not p.exists() or not p.is_file():
            raise RuntimeError(f"local_not_found:{tenant_id}:{key}")
        return str(p.resolve())

    # ====== Extra helpers voor verify/move (local) ======
    def _head_local(self, tenant_id: str, key: str) -> Optional[Dict]:
        p = self._full_path(tenant_id, key)
        if not p.exists() or not p.is_file():
            return None
        try:
            st = p.stat()
            size = st[stat.ST_SIZE]
            ctype, _ = mimetypes.guess_type(str(p))
            return {
                "ContentLength": size,
                "ContentType": ctype or "application/octet-stream",
            }
        except Exception as e:
            logger.error("Local head error %s: %s", p, e)
            return None

    def _copy_local(self, tenant_id: str, src_key: str, dst_key: str) -> None:
        src = self._full_path(tenant_id, src_key)
        dst = self._full_path(tenant_id, dst_key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    def _move_local(self, tenant_id: str, src_key: str, dst_key: str) -> None:
        self._copy_local(tenant_id, src_key, dst_key)
        self.delete(tenant_id, src_key)


# =========================
# S3 Storage
# =========================
class S3Storage(Storage):
    """Amazon S3 bestandsopslag implementatie."""

    def __init__(
        self,
        bucket: str,
        region: str = "eu-west-1",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None,
        aws_profile: Optional[str] = None,
        *,
        verify_bucket_on_startup: bool = True,
    ):
        self.bucket = bucket

        # --- Create session (supports AWS_PROFILE + env/instance creds + optional raw creds) ---
        session_kwargs: dict = {}
        if aws_profile:
            session_kwargs["profile_name"] = aws_profile

        # region_name kan je op session zetten, maar client override is ook ok.
        session = boto3.Session(**session_kwargs)

        client_kwargs: dict = {"region_name": region}

        # Only pass explicit creds if provided (otherwise use profile/env/role chain)
        if aws_access_key_id and aws_secret_access_key:
            client_kwargs["aws_access_key_id"] = aws_access_key_id
            client_kwargs["aws_secret_access_key"] = aws_secret_access_key
            if aws_session_token:
                client_kwargs["aws_session_token"] = aws_session_token

        # 1) bootstrap in opgegeven region om bucket-locatie te bepalen
        bootstrap = session.client("s3", **client_kwargs)
        try:
            loc = bootstrap.get_bucket_location(Bucket=bucket).get("LocationConstraint")
            self.region = loc or "us-east-1"
        except Exception as e:
            logger.warning(
                "Kon bucket location niet bepalen, val terug op region=%s. Error: %s",
                region,
                e,
            )
            self.region = region

        # 2) definitive client in juiste region
        client_kwargs["region_name"] = self.region
        self.s3_client = session.client("s3", **client_kwargs)

        if verify_bucket_on_startup:
            try:
                self.s3_client.head_bucket(Bucket=bucket)
                logger.info(
                    "S3 bucket %s is toegankelijk (region=%s)", bucket, self.region
                )
            except (ClientError, NoCredentialsError) as e:
                logger.error("Kan geen toegang krijgen tot S3 bucket %s: %s", bucket, e)
                raise

    def _tenant_key(self, tenant_id: str, key: str) -> str:
        tenant_id = (tenant_id or "").strip().strip("/")
        key = (key or "").strip().lstrip("/")
        if not tenant_id:
            return key
        prefix = f"{tenant_id}/"
        return key if key.startswith(prefix) else prefix + key

    def _guess_content_type(self, key: str) -> str:
        ext = Path(key).suffix.lower()
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".txt": "text/plain; charset=utf-8",
            ".json": "application/json; charset=utf-8",
        }
        if ext in content_types:
            return content_types[ext]
        mt, _ = mimetypes.guess_type(key)
        return mt or "application/octet-stream"

    def head(self, tenant_id: str, key: str) -> Dict:
        meta = self.head_object(tenant_id, key)
        if not meta:
            raise RuntimeError("not_found")
        return {
            "size_bytes": int(meta.get("ContentLength", 0) or 0),
            "content_type": str(meta.get("ContentType") or ""),
        }

    def presigned_get_url(
        self, tenant_id: str, key: str, expires_seconds: int = 3600
    ) -> str:
        s3_key = self._tenant_key(tenant_id, key)
        return self.s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": self.bucket, "Key": s3_key},
            ExpiresIn=expires_seconds,
        )

    def save_bytes(
        self,
        tenant_id: str,
        key: str,
        data: bytes,
        *,
        content_type: Optional[str] = None,
    ) -> str:
        s3_key = self._tenant_key(tenant_id, key)
        try:
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=data,
                ContentType=content_type or self._guess_content_type(key),
            )
            logger.info("S3 uploaded: %s", s3_key)
            return key
        except Exception as e:
            logger.error("S3 upload error key=%s: %s", s3_key, e)
            raise RuntimeError(f"s3_upload_failed:{s3_key}:{type(e).__name__}:{e}")

    def download_to_temp_path(self, tenant_id: str, key: str) -> str:
        s3_key = self._tenant_key(tenant_id, key)
        suffix = Path(key).suffix or ".bin"
        fd, tmp_path = tempfile.mkstemp(prefix="aether_", suffix=suffix)
        try:
            import os

            os.close(fd)
        except Exception:
            pass

        try:
            self.s3_client.download_file(self.bucket, s3_key, tmp_path)
            return str(Path(tmp_path).resolve())
        except ClientError as e:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
            raise RuntimeError(f"s3_download_failed:{s3_key}:{e}")
        except Exception as e:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass
            raise RuntimeError(f"s3_download_failed:{s3_key}:{type(e).__name__}:{e}")

    def public_url(self, tenant_id: str, key: str) -> str:
        s3_key = quote(self._tenant_key(tenant_id, key), safe="/")
        if self.region == "us-east-1":
            return f"https://{self.bucket}.s3.amazonaws.com/{s3_key}"
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{s3_key}"

    def exists(self, tenant_id: str, key: str) -> bool:
        try:
            s3_key = self._tenant_key(tenant_id, key)
            self.s3_client.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in {"404", "NotFound"}:
                return False
            logger.error("S3 exists head error key=%s: %s", key, e)
            return False
        except Exception as e:
            logger.error("S3 exists unexpected key=%s: %s", key, e)
            return False

    def delete(self, tenant_id: str, key: str) -> bool:
        try:
            s3_key = self._tenant_key(tenant_id, key)
            self.s3_client.delete_object(Bucket=self.bucket, Key=s3_key)
            logger.info("S3 deleted: %s", s3_key)
            return True
        except Exception as e:
            logger.error("S3 delete error key=%s: %s", key, e)
            return False

    # ====== Extra helpers voor verify/move (S3) ======
    def head_object(self, tenant_id: str, key: str) -> Optional[Dict]:
        try:
            r = self.s3_client.head_object(
                Bucket=self.bucket, Key=self._tenant_key(tenant_id, key)
            )
            return {
                "ContentLength": r.get("ContentLength", 0),
                "ContentType": r.get("ContentType", ""),
            }
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code in {"404", "NotFound"}:
                return None
            logger.error("S3 head_object error key=%s: %s", key, e)
            return None

    def copy_object(self, tenant_id: str, src_key: str, dst_key: str) -> None:
        full_src = self._tenant_key(tenant_id, src_key)
        self.s3_client.copy_object(
            Bucket=self.bucket,
            CopySource={"Bucket": self.bucket, "Key": full_src},
            Key=self._tenant_key(tenant_id, dst_key),
        )

    def move_object(self, tenant_id: str, src_key: str, dst_key: str) -> None:
        self.copy_object(tenant_id, src_key, dst_key)
        self.delete(tenant_id, src_key)


# =========================
# Factory
# =========================
from typing import Optional


def get_storage() -> Storage:
    """
    Select storage backend based on settings.STORAGE_BACKEND.

    IMPORTANT:
    - We do NOT silently default to local in production-like environments.
    - If STORAGE_BACKEND is missing, we either:
      - default to local only in explicit local/dev environments, OR
      - raise loudly (recommended).
    """
    backend_raw = (settings.STORAGE_BACKEND or "").strip().lower()

    # Detect environment (best-effort; supports common names)
    env_raw = (
        (
            (getattr(settings, "ENVIRONMENT", None) or "")
            or (getattr(settings, "APP_ENV", None) or "")
            or (getattr(settings, "ENV", None) or "")
        )
        .strip()
        .lower()
    )

    # If STORAGE_BACKEND not set, be strict.
    # Default to local ONLY when clearly running locally/dev.
    if not backend_raw:
        if env_raw in ("prod", "production", "staging"):
            raise ValueError(
                "STORAGE_BACKEND must be set to 's3' in production/staging"
            )
        # If env isn't provided, still prefer to fail loudly to avoid surprises.
        # If you *really* want a fallback in dev, set ENVIRONMENT=local or STORAGE_BACKEND=local.
        raise ValueError("STORAGE_BACKEND is required (set to 'local' or 's3')")

    storage_backend = backend_raw

    if storage_backend == "s3":
        bucket = (settings.S3_BUCKET or "").strip()
        region = (settings.AWS_REGION or "").strip() or None

        if not bucket:
            raise ValueError(
                "S3_BUCKET environment variable is vereist voor S3 storage"
            )

        aws_profile: Optional[str] = getattr(settings, "AWS_PROFILE", None)
        aws_session_token: Optional[str] = getattr(settings, "AWS_SESSION_TOKEN", None)

        return S3Storage(
            bucket=bucket,
            region=region,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            aws_session_token=aws_session_token,
            aws_profile=aws_profile,
            verify_bucket_on_startup=False,
        )

    if storage_backend == "local":
        base_path = getattr(settings, "LOCAL_STORAGE_PATH", None) or getattr(
            settings, "LOCAL_STORAGE_ROOT", None
        )
        if not base_path:
            raise ValueError(
                "LOCAL_STORAGE_PATH (of LOCAL_STORAGE_ROOT) is vereist voor local storage"
            )
        return LocalStorage(base_path=base_path)

    raise ValueError(f"Onbekende storage backend: {storage_backend!r}")


# =========================
# Simple helpers (text/html/json)
# =========================
def put_text(
    storage: Storage,
    tenant_id: str,
    key: str,
    text: str,
    content_type: str = "text/plain; charset=utf-8",
) -> str:
    return storage.save_bytes(
        tenant_id, key, text.encode("utf-8"), content_type=content_type
    )


def get_text(storage: Storage, tenant_id: str, key: str) -> str:
    tmp_path = storage.download_to_temp_path(tenant_id, key)
    p = Path(tmp_path)
    try:
        return p.read_text(encoding="utf-8")
    finally:
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass


# =========================
# Verify + finalize helpers
# =========================
def _basic_key_checks(key: str) -> Optional[str]:
    if not key:
        return "empty_key"
    if key.startswith("/") or key.endswith("/"):
        return "bad_slashes"
    if ".." in key:
        return "path_traversal"
    if not key.startswith(TEMP_PREFIX):
        return "wrong_prefix"
    return None


def head_ok(
    storage: Storage, tenant_id: str, key: str
) -> Tuple[bool, Optional[Dict], Optional[str]]:
    err = _basic_key_checks(key)
    if err:
        return False, None, err

    meta: Optional[Dict] = None
    if isinstance(storage, S3Storage):
        meta = storage.head_object(tenant_id, key)
    elif isinstance(storage, LocalStorage):
        meta = storage._head_local(tenant_id, key)  # type: ignore[attr-defined]
    else:
        logger.error("Unsupported storage backend voor head_ok")
        return False, None, "unsupported_backend"

    if not meta:
        return False, None, "head_not_found"

    size = int(meta.get("ContentLength", 0) or 0)
    ctype = str(meta.get("ContentType") or "")

    if size <= 0 or size > MAX_BYTES:
        return False, meta, "size_exceeded"
    if ALLOWED_CONTENT_TYPES and ctype not in ALLOWED_CONTENT_TYPES:
        return False, meta, "bad_content_type"

    return True, meta, None


def finalize_move(storage: Storage, tenant_id: str, temp_key: str, lead_id: str) -> str:
    filename = temp_key.split("/")[-1]
    final_key = f"{FINAL_PREFIX}{lead_id}/{filename}"

    if isinstance(storage, S3Storage):
        storage.move_object(tenant_id, temp_key, final_key)
    elif isinstance(storage, LocalStorage):
        storage._move_local(tenant_id, temp_key, final_key)  # type: ignore[attr-defined]
    else:
        raise RuntimeError("Unsupported storage backend bij finalize_move")

    return final_key

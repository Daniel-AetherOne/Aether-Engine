from functools import lru_cache
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Tuple, Iterable
import io
import boto3
from app.core.settings import settings


@lru_cache(maxsize=1)
def s3_client():
    """
    Returns a cached boto3 S3 client configured from Settings.
    """
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        config=boto3.session.Config(signature_version="s3v4"),
    )

def _safe_filename(name: str) -> str:
    """Maak bestandsnaam S3-veilig."""
    name = name.strip().replace(" ", "-")
    name = name.split("/")[-1].split("\\")[-1]
    cleaned = SAFE_CHARS_RE.sub("-", name)
    return cleaned or f"file-{uuid.uuid4().hex}"


def _guess_content_type(filename: str, fallback: str = "application/octet-stream") -> str:
    ctype, _ = mimetypes.guess_type(filename)
    return ctype or fallback


@dataclass(frozen=True)
class S3ObjectRef:
    bucket: str
    key: str

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


class S3Service:
    """Dunne wrapper rond boto3 S3 client met helpers + nette logging."""

    def __init__(self) -> None:
        s = get_settings()

        boto_cfg = BotoConfig(
            region_name=s.AWS_REGION,
            retries={"max_attempts": 5, "mode": "standard"},
            signature_version="s3v4",
            connect_timeout=5,
            read_timeout=30,
        )

        session = boto3.session.Session(
            aws_access_key_id=s.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=s.AWS_SECRET_ACCESS_KEY,
            aws_session_token=s.AWS_SESSION_TOKEN,
            region_name=s.AWS_REGION,
        )

        self.client = session.client(
            "s3",
            endpoint_url=str(s.S3_ENDPOINT_URL) if s.S3_ENDPOINT_URL else None,
            config=boto_cfg,
        )
        self.bucket = s.S3_BUCKET
        self._default_expires = s.PRESIGN_EXPIRES_SECONDS

        logger.info(
            f"s3_client_ready bucket={self.bucket} region={s.AWS_REGION} "
            f"endpoint={'custom' if s.S3_ENDPOINT_URL else 'aws'}"
        )

    # ---------- key builder ----------
    def build_key(
        self,
        *,
        lead_id: str,
        kind: str,
        original_filename: str,
        extra: Optional[str] = None,
    ) -> str:
        """Bouw een consistente object key voor uploads."""
        safe_name = _safe_filename(original_filename)
        uid = uuid.uuid4().hex[:12]
        today = time.strftime("%Y/%m/%d")

        parts = ["leads", today, lead_id, kind]
        if extra:
            parts.append(_safe_filename(extra))
        fn = f"{uid}-{safe_name}"
        key = "/".join(parts + [fn])

        logger.debug(f"s3_build_key key={key} lead_id={lead_id} kind={kind}")
        return key

    # ---------- upload helpers ----------
    def put_fileobj(
        self,
        fileobj: io.BufferedReader | io.BytesIO,
        key: str,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> S3ObjectRef:
        """
        Upload een stream/buffer naar S3 als object.
        """
        start = time.perf_counter()
        try:
            ct = content_type or "application/octet-stream"
            extra: Dict[str, Any] = {"ContentType": ct}
            if metadata:
                extra["Metadata"] = metadata

            logger.info(f"s3_put start key={key} content_type={ct}")
            self.client.upload_fileobj(fileobj, self.bucket, key, ExtraArgs=extra)
            dur = (time.perf_counter() - start) * 1000
            logger.info(f"s3_put ok key={key} duration_ms={dur:.1f}")
            return S3ObjectRef(self.bucket, key)
        except (ClientError, BotoCoreError) as e:
            dur = (time.perf_counter() - start) * 1000
            logger.error(f"s3_put failed key={key} duration_ms={dur:.1f} error={e}")
            raise

    def put_bytes(
        self,
        data: bytes,
        key: str,
        *,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> S3ObjectRef:
        """Upload bytes naar S3."""
        bio = io.BytesIO(data)
        if content_type is None:
            # Probeer af te leiden uit bestandsnaam
            content_type = _guess_content_type(key)
        return self.put_fileobj(bio, key, content_type=content_type, metadata=metadata)

    # ---------- presigned URLs ----------
    def presigned_get(self, key: str, *, expires_in: Optional[int] = None) -> str:
        start = time.perf_counter()
        try:
            exp = expires_in or self._default_expires
            logger.info(f"s3_presign_get start key={key} expires={exp}")
            url = self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=exp,
            )
            dur = (time.perf_counter() - start) * 1000
            logger.info(f"s3_presign_get ok key={key} duration_ms={dur:.1f}")
            return url
        except (ClientError, BotoCoreError) as e:
            dur = (time.perf_counter() - start) * 1000
            logger.error(f"s3_presign_get failed key={key} duration_ms={dur:.1f} error={e}")
            raise

    def presigned_post(
        self,
        key: str,
        *,
        content_type: Optional[str] = None,
        max_size: int = 25 * 1024 * 1024,  # 25 MB
        expires_in: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Maak een presigned POST (client kan direct naar S3 uploaden).
        """
        start = time.perf_counter()
        try:
            exp = expires_in or self._default_expires
            conditions: list[Any] = [["content-length-range", 1, max_size]]
            fields: Dict[str, Any] = {}
            if content_type:
                fields["Content-Type"] = content_type
                conditions.append({"Content-Type": content_type})

            logger.info(
                f"s3_presign_post start key={key} expires={exp} "
                f"max_size={max_size} content_type={content_type}"
            )
            resp = self.client.generate_presigned_post(
                Bucket=self.bucket,
                Key=key,
                Fields=fields or None,
                Conditions=conditions or None,
                ExpiresIn=exp,
            )
            dur = (time.perf_counter() - start) * 1000
            logger.info(f"s3_presign_post ok key={key} duration_ms={dur:.1f}")
            return resp
        except (ClientError, BotoCoreError) as e:
            dur = (time.perf_counter() - start) * 1000
            logger.error(f"s3_presign_post failed key={key} duration_ms={dur:.1f} error={e}")
            raise

    # ---------- management ----------
    def head(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Haal meta op van een object, of None bij 404.
        """
        start = time.perf_counter()
        try:
            logger.info(f"s3_head start key={key}")
            resp = self.client.head_object(Bucket=self.bucket, Key=key)
            dur = (time.perf_counter() - start) * 1000
            size = resp.get("ContentLength")
            etag = resp.get("ETag")
            logger.info(f"s3_head ok key={key} size={size} etag={etag} duration_ms={dur:.1f}")
            return resp
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            dur = (time.perf_counter() - start) * 1000
            if code in {"404", "NotFound", "NoSuchKey"}:
                logger.info(f"s3_head not_found key={key} duration_ms={dur:.1f}")
                return None
            logger.error(f"s3_head failed key={key} duration_ms={dur:.1f} error={e}")
            raise
        except BotoCoreError as e:
            dur = (time.perf_counter() - start) * 1000
            logger.error(f"s3_head failed key={key} duration_ms={dur:.1f} error={e}")
            raise

    def delete(self, key: str) -> None:
        start = time.perf_counter()
        try:
            logger.info(f"s3_delete start key={key}")
            self.client.delete_object(Bucket=self.bucket, Key=key)
            dur = (time.perf_counter() - start) * 1000
            logger.info(f"s3_delete ok key={key} duration_ms={dur:.1f}")
        except (ClientError, BotoCoreError) as e:
            dur = (time.perf_counter() - start) * 1000
            logger.error(f"s3_delete failed key={key} duration_ms={dur:.1f} error={e}")
            raise

    def list_prefix(self, prefix: str, *, limit: int = 1000) -> Iterable[Dict[str, Any]]:
        """
        Listeer objecten onder een prefix (max = limit items).
        """
        start = time.perf_counter()
        try:
            logger.info(f"s3_list start prefix={prefix} limit={limit}")
            paginator = self.client.get_paginator("list_objects_v2")
            count = 0
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for item in page.get("Contents", []) or []:
                    yield item
                    count += 1
                    if count >= limit:
                        dur = (time.perf_counter() - start) * 1000
                        logger.info(f"s3_list ok prefix={prefix} returned={count} duration_ms={dur:.1f}")
                        return
            dur = (time.perf_counter() - start) * 1000
            logger.info(f"s3_list ok prefix={prefix} returned={count} duration_ms={dur:.1f}")
        except (ClientError, BotoCoreError) as e:
            dur = (time.perf_counter() - start) * 1000
            logger.error(f"s3_list failed prefix={prefix} duration_ms={dur:.1f} error={e}")
            raise

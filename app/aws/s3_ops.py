# app/aws/s3_ops.py
import logging
from botocore.exceptions import ClientError, EndpointConnectionError, ConnectTimeoutError, ReadTimeoutError
from app.infra.s3_client import get_s3, get_bucket
from app.infra.retry import retry_on

logger = logging.getLogger(__name__)

_RETRY_404_CODES = {"NoSuchKey", "NotFound"}
_RETRY_CODES = {
    "SlowDown", "Throttling", "RequestTimeout",
    "InternalError", "ServiceUnavailable", "InternalServerError",
}

def _is_retryable_s3(exc: Exception) -> bool:
    # Netwerk/endpoint timeouts
    if isinstance(exc, (EndpointConnectionError, ConnectTimeoutError, ReadTimeoutError)):
        return True
    if isinstance(exc, ClientError):
        err = exc.response.get("Error", {}) or {}
        code = err.get("Code")
        http = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        # 404 race conditions
        if code in _RETRY_404_CODES:
            return True
        # Throttling/timeout/5xx
        if code in _RETRY_CODES:
            return True
        if isinstance(http, int) and 500 <= http < 600:
            return True
    return False

def _log_retry(attempt: int, exc: Exception, sleep_s: float):
    try:
        code = None
        if isinstance(exc, ClientError):
            code = exc.response.get("Error", {}).get("Code")
        logger.warning("S3 retry #%d in %.2fs (code=%s, exc=%s)", attempt, sleep_s, code, type(exc).__name__)
    except Exception:
        logger.warning("S3 retry #%d in %.2fs (exc=%s)", attempt, sleep_s, type(exc).__name__)

def get_object_with_retry(key: str):
    s3 = get_s3()
    bucket = get_bucket()
    return retry_on(
        lambda: s3.get_object(Bucket=bucket, Key=key),
        attempts=3, base=0.2, factor=2.0, cap=2.0,
        is_retryable=_is_retryable_s3, on_retry=_log_retry
    )

def delete_object_with_retry(key: str):
    s3 = get_s3()
    bucket = get_bucket()
    return retry_on(
        lambda: s3.delete_object(Bucket=bucket, Key=key),
        attempts=3, base=0.2, factor=2.0, cap=2.0,
        is_retryable=_is_retryable_s3, on_retry=_log_retry
    )

def head_object_with_retry(key: str):
    s3 = get_s3()
    bucket = get_bucket()
    return retry_on(
        lambda: s3.head_object(Bucket=bucket, Key=key),
        attempts=3, base=0.2, factor=2.0, cap=2.0,
        is_retryable=_is_retryable_s3, on_retry=_log_retry
    )

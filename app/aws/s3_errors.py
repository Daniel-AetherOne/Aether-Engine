# app/aws/s3_errors.py
import logging
from typing import Tuple, Dict, Any, Optional
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

def map_s3_client_error(e: ClientError) -> Tuple[int, Dict[str, Any]]:
    err = e.response.get("Error", {}) or {}
    meta = e.response.get("ResponseMetadata", {}) or {}

    code: str = err.get("Code", "")
    msg: str = err.get("Message", "") or str(e)
    http_status: int = int(meta.get("HTTPStatusCode", 500))
    aws_request_id: Optional[str] = meta.get("RequestId")

    # Standaardwaarden
    status = 502
    hint = None

    # Veelvoorkomende cases
    if code in {"NoSuchKey", "NotFound"}:
        status = 404
        hint = "Key bestaat niet of is nog niet gecommit; probeer kort opnieuw."
    elif code in {"AccessDenied"}:
        status = 403
        hint = "Controleer IAM/bucket policy (s3:GetObject/HeadObject/PutObject)."
    elif code in {"SignatureDoesNotMatch"}:
        status = 403
        hint = "Controleer AWS_REGION vs bucket-regio en tijdsync (NTP)."
    elif code in {"InvalidRequest", "PolicyConditionFailed"} or http_status == 400:
        status = 400
        hint = "Upload/aanvraag voldoet niet aan policy (Content-Type of bestandsgrootte matcht Conditions niet)."
    elif 500 <= http_status < 600:
        status = 502
        hint = "Tijdelijke S3-storing; probeer zo opnieuw."
    elif code in {"RequestTimeout", "SlowDown", "Throttling"}:
        status = 429
        hint = "S3 throttling/timeout; probeer zo opnieuw."

    body = {
        "ok": False,
        "error": {
            "type": "S3ClientError",
            "code": code,
            "message": msg,
            "hint": hint,
            "aws_request_id": aws_request_id,
            "aws_http": http_status,
        },
    }
    return status, body

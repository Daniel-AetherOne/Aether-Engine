# app/routers/debug_s3.py  (of hernoem je bestaande debu_s3.py naar debug_s3.py)
import logging
from fastapi import APIRouter, HTTPException
from botocore.exceptions import ClientError, EndpointConnectionError
from app.infra.s3_client import get_s3, get_bucket, get_region

router = APIRouter(prefix="/debug", tags=["debug"])
logger = logging.getLogger(__name__)

from app.infra.s3_client import get_s3, get_bucket


@router.get("/s3-list")
def s3_list(prefix: str = "", max_keys: int = 10):
    """
    Geeft een lijst van de eerste X objecten in je S3 bucket (handig om te testen).
    """
    resp = get_s3().list_objects_v2(Bucket=get_bucket(), Prefix=prefix, MaxKeys=max_keys)
    keys = [it["Key"] for it in resp.get("Contents", [])]
    return {"bucket": get_bucket(), "count": len(keys), "keys": keys}


def _hint_for_code(code: str | None) -> str | None:
    if code == "SignatureDoesNotMatch":
        return "Controleer AWS_REGION vs bucket-regio en tijdsync (NTP)."
    if code == "AccessDenied":
        return "Controleer IAM/bucket policy (s3:HeadBucket, s3:GetBucketLocation)."
    if code == "NoSuchBucket":
        return "Controleer de waarde van S3_BUCKET; bucket bestaat niet."
    return None

def _s3_status():
    s3 = get_s3()
    bucket = get_bucket()
    configured_region = get_region()

    try:
        # Snelste ‘bestaat bucket / heb ik toegang’ check:
        s3.head_bucket(Bucket=bucket)

        # Handig voor regio-debugging:
        loc_resp = s3.get_bucket_location(Bucket=bucket)
        bucket_region = loc_resp.get("LocationConstraint")

        return {
            "status": "ok",
            "bucket": bucket,
            "configured_region": configured_region,
            "bucket_region": bucket_region,
        }

    except EndpointConnectionError as e:
        # Netwerk/DNS/VPC endpoint issues
        logger.error("S3 endpoint connection error: %s", e)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "code": "EndpointConnectionError",
                "message": str(e),
                "hint": "Controleer netwerk/VPC endpoint/DNS en AWS_REGION endpoint.",
            },
        )

    except ClientError as e:
        err = e.response.get("Error", {}) or {}
        meta = e.response.get("ResponseMetadata", {}) or {}

        code = err.get("Code")
        aws_request_id = meta.get("RequestId")
        aws_http = meta.get("HTTPStatusCode", 503)

        # Basis mapping naar HTTP-status
        status = 503
        if code in {"SignatureDoesNotMatch", "AccessDenied"}:
            status = 403
        elif code in {"NoSuchBucket"}:
            status = 404

        logger.error(
            "S3 debug check failed code=%s http=%s aws_request_id=%s",
            code, aws_http, aws_request_id
        )

        raise HTTPException(
            status_code=status,
            detail={
                "status": "error",
                "code": code,
                "aws_http": aws_http,
                "aws_request_id": aws_request_id,
                "hint": _hint_for_code(code),
            },
        )

@router.get("/s3-check")
def s3_check_get():
    return _s3_status()

@router.post("/s3-check")
def s3_check_post():
    return _s3_status()

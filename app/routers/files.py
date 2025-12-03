# app/routers/files.py
from uuid import uuid4
from fastapi import APIRouter, Query
from pydantic import BaseModel
import boto3

from app.core.settings import settings


router = APIRouter(prefix="/files", tags=["files"])


def get_s3_client():
    return boto3.client(
        "s3",
        region_name=settings.S3_REGION,  # komt uit app/core/settings.py
        # credentials haalt boto3 uit ~/.aws/credentials, dat zie je al in de logs
    )



class PresignUploadResponse(BaseModel):
    url: str
    fields: dict
    key: str


@router.get("/presign-upload", response_model=PresignUploadResponse)
def presign_upload(
    filename: str = Query(...),
    content_type: str = Query("image/jpeg"),
):
    """
    Geeft een presigned POST terug zodat de browser direct kan uploaden naar S3.
    """
    s3_client = get_s3_client()

    # Pad in de bucket waar intake-foto's komen
    key = f"intake-uploads/{uuid4()}/{filename}"

    presigned = s3_client.generate_presigned_post(
        Bucket=settings.S3_BUCKET,   # <-- NIET S3_BUCKET_NAME
        Key=key,
        Fields={"Content-Type": content_type},
        Conditions=[{"Content-Type": content_type}],
        ExpiresIn=3600,
    )


    return PresignUploadResponse(
        url=presigned["url"],
        fields=presigned["fields"],
        key=key,
    )

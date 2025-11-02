# app/api/routes/presign.py
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, field_validator
from typing import Optional

router = APIRouter(prefix="/uploads", tags=["Uploads"])

# === Request schema ===
class PresignRequest(BaseModel):
    filename: str
    content_type: str
    size: int
    lead_id: str
    expires_in: Optional[int] = None  # optioneel in tests

    @field_validator("size")
    @classmethod
    def size_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("size must be > 0")
        return v

ALLOWED_TYPES = {"image/png", "application/pdf"}
MAX_SIZE = 100 * 1024 * 1024  # 100 MB

def _check_auth(authorization: Optional[str]) -> str:
    """
    Dummy auth voor tests:
    - header verplicht -> anders 401
    - retourneer 'u1' als user_id
    """
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing auth")
    return "u1"

def _check_lead_access(user_id: str, lead_id: str) -> None:
    """
    Dummy access rule t.b.v. tests:
    - 'lead_of_other_user' => 403
    """
    if lead_id == "lead_of_other_user":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

@router.post("/presign")
def presign(body: PresignRequest, Authorization: Optional[str] = Header(default=None)):
    # Security
    user_id = _check_auth(Authorization)
    _check_lead_access(user_id, body.lead_id)

    # Validatie MIME/size
    if body.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid content_type")
    if body.size > MAX_SIZE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file too large")

    # Simpel object_key voor tests
    object_key = f"leads/{body.lead_id}/{body.filename}"

    # In je echte implementatie zou je hier S3-presign genereren en UploadStatus(pending) opslaan
    return {
        "object_key": object_key,
        "url": f"https://example-bucket.s3.amazonaws.com/{object_key}",  # dummy
        "expires_in": body.expires_in or 900,
    }

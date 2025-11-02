from pydantic import BaseModel, Field

class PresignRequest(BaseModel):
    filename: str = Field(..., min_length=1)
    content_type: str
    size_bytes: int = Field(..., gt=0)
    lead_id: str
    checksum_sha256: str | None = None

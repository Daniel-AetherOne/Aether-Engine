# app/schemas/uploads_multipart.py
from pydantic import BaseModel, Field
from typing import List, Dict

class MPUStartIn(BaseModel):
    lead_id: int
    content_type: str
    metadata: Dict[str, str] | None = None

class MPUStartOut(BaseModel):
    upload_id: str
    object_key: str
    part_size: int
    url_expires_in: int

class MPUGetPartURLsIn(BaseModel):
    lead_id: int
    object_key: str
    upload_id: str
    part_numbers: List[int]

class MPUGetPartURLsOut(BaseModel):
    parts: List[Dict]  # [{part_number, url}]

class MPUCompleteIn(BaseModel):
    lead_id: int
    object_key: str
    upload_id: str
    parts: List[Dict]  # [{part_number, etag}]

class MPUAbortIn(BaseModel):
    lead_id: int
    object_key: str
    upload_id: str

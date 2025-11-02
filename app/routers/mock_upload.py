from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from uuid import uuid4
from pathlib import Path
import hashlib, json

router = APIRouter(prefix="/api", tags=["mock-upload"])

STORAGE_ROOT = Path("app/mock_storage")
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

class AttachPayload(BaseModel):
    lead_id: str
    key: str
    original_name: str
    size: int
    content_type: str
    public_url: str | None = None

@router.get("/storage/presign/put")
def presign_put(filename: str, content_type: str, size: int):
    key = f"mock/{uuid4().hex}/{filename}"
    url = f"/api/mock/put/{key}"
    public_url = f"/api/mock/objects/{key}"
    return {"url": url, "headers": {}, "key": key, "public_url": public_url}

@router.put("/mock/put/{key:path}")
async def mock_put(key: str, request: Request):
    body = await request.body()
    if not body:
        raise HTTPException(400, "Empty body")
    target = STORAGE_ROOT / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    etag = hashlib.md5(body).hexdigest()
    return JSONResponse({"ok": True, "bytes": len(body), "key": key}, headers={"ETag": f"\"{etag}\""})

@router.get("/mock/objects/{key:path}")
def mock_get_object(key: str):
    path = STORAGE_ROOT / key
    if not path.exists():
        raise HTTPException(404, "Not found")
    return FileResponse(path)

@router.post("/intake/attach")
def mock_attach(payload: AttachPayload):
    (STORAGE_ROOT / "attachments.log").open("a", encoding="utf-8").write(json.dumps(payload.model_dump()) + "\n")
    return {"ok": True, "attached": payload.model_dump()}

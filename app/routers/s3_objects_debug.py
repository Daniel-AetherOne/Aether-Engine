from fastapi import APIRouter
from app.aws.s3_ops import get_object_with_retry, delete_object_with_retry, head_object_with_retry

router = APIRouter(prefix="/debug/s3obj", tags=["debug-s3"])

@router.get("/{key:path}")
def get_obj(key: str):
    obj = get_object_with_retry(key)     # laat ClientError door
    return {"key": key, "content_length": obj["ContentLength"]}

@router.delete("/{key:path}")
def del_obj(key: str):
    delete_object_with_retry(key)        # laat ClientError door
    return {"deleted": key}

@router.get("/head/{key:path}")
def head_obj(key: str):
    head = head_object_with_retry(key)   # laat ClientError door
    return {"key": key, "content_length": head["ContentLength"]}

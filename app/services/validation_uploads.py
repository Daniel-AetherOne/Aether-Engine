from app.config_uploads import upload_settings

def validate_mime(content_type: str) -> None:
    allowed = {m.strip() for m in upload_settings.allowed_upload_mime.split(",") if m.strip()}
    if content_type not in allowed:
        raise ValueError(f"MIME-type niet toegestaan: {content_type}")

def validate_size(size_bytes: int) -> None:
    max_bytes = upload_settings.max_upload_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise ValueError(f"Bestand is te groot (>{upload_settings.max_upload_mb} MB)")

def checksum_required() -> bool:
    return bool(upload_settings.require_checksum)

from fastapi import Header, HTTPException, Request, Depends
from typing import Optional
import re
from app.services.tenant_service import TenantService
from app.services.storage import Storage, get_storage
from __future__ import annotations

# Global service instances
tenant_service = TenantService()


def get_storage_service() -> Storage:
    return get_storage()


async def resolve_tenant(
    request: Request, x_tenant: Optional[str] = Header(None, alias="X-Tenant")
) -> str:
    """
    Resolve tenant from X-Tenant header or subdomain.
    Returns tenant_id or raises HTTPException if not found.
    """
    tenant_id = None

    # First try X-Tenant header
    if x_tenant:
        tenant_id = x_tenant.strip()

    # Fallback to subdomain extraction
    if not tenant_id:
        host = request.headers.get("host", "")
        if host:
            # Extract subdomain (e.g., tenant1.localhost:8000 -> tenant1)
            subdomain_match = re.match(r"^([^.]+)\.", host)
            if subdomain_match:
                tenant_id = subdomain_match.group(1)

    # Default tenant if none specified
    if not tenant_id:
        tenant_id = "default"

    # Validate tenant exists
    try:
        tenant = tenant_service.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=400, detail=f"Invalid tenant_id: {tenant_id}"
            )
        return tenant_id
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resolving tenant: {str(e)}")


async def get_tenant_settings(tenant_id: str = Depends(resolve_tenant)):
    """
    Get tenant settings for the resolved tenant_id.
    This dependency can be used in route handlers to get tenant configuration.
    """
    return tenant_service.get_tenant(tenant_id)


async def get_tenant_storage_path(
    base_path: str, tenant_id: str = Depends(resolve_tenant)
):
    """
    Get tenant-specific storage path for the given base path.
    """
    return tenant_service.get_tenant_storage_path(tenant_id, base_path)


async def get_storage_service():
    """
    Get storage service instance.
    This dependency can be used in route handlers to get storage functionality.
    """
    return storage_service


from functools import lru_cache
from app.services.s3 import S3Service


@lru_cache(maxsize=1)
def get_s3_service() -> S3Service:
    """Singleton S3 client for FastAPI DI."""
    return S3Service()

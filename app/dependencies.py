from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request

from app.services.s3 import S3Service
from app.services.storage import Storage, get_storage
from app.services.tenant_service import TenantService

# Global service instances
tenant_service = TenantService()


def get_storage_service() -> Storage:
    """Sync helper to access the storage implementation (S3/local/etc)."""
    return get_storage()


async def resolve_tenant(
    request: Request,
    x_tenant: Optional[str] = Header(None, alias="X-Tenant"),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-Id"),
) -> str:
    """
    Resolve tenant from headers or subdomain.

    Priority:
    1) X-Tenant-Id
    2) X-Tenant
    3) subdomain: <tenant>.localhost:8000
    4) local dev fallback: 127.0.0.1 / localhost -> dev-tenant
    5) default -> "default"

    Returns tenant_id or raises HTTPException.
    """
    tenant_id: Optional[str] = None

    # 1) Headers
    header_val = (x_tenant_id or x_tenant or "").strip()
    if header_val:
        tenant_id = header_val

    # 2) Subdomain extraction
    if not tenant_id:
        host = (request.headers.get("host") or "").strip()
        if host:
            # Extract subdomain (e.g., tenant1.localhost:8000 -> tenant1)
            subdomain_match = re.match(r"^([^.]+)\.", host)
            if subdomain_match:
                tenant_id = subdomain_match.group(1)

    # 3) Local dev fallback (no subdomain on 127.0.0.1 / localhost)
    if not tenant_id:
        host = (request.headers.get("host") or "").strip()
        if host.startswith("127.0.0.1") or host.startswith("localhost"):
            tenant_id = "dev-tenant"

    # 4) Final fallback
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

    except HTTPException:
        # Keep explicit HTTP errors (like invalid tenant) intact
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resolving tenant: {str(e)}")


async def get_tenant_settings(tenant_id: str = Depends(resolve_tenant)):
    """
    Get tenant settings for the resolved tenant_id.
    """
    return tenant_service.get_tenant(tenant_id)


async def get_tenant_storage_path(
    base_path: str, tenant_id: str = Depends(resolve_tenant)
):
    """
    Get tenant-specific storage path for the given base path.
    """
    return tenant_service.get_tenant_storage_path(tenant_id, base_path)


@lru_cache(maxsize=1)
def get_s3_service() -> S3Service:
    """Singleton S3 client for FastAPI DI."""
    return S3Service()

from fastapi import APIRouter, HTTPException, Depends
from typing import List
from app.models.tenant_settings import TenantSettings
from app.services.tenant_service import TenantService
from app.dependencies import resolve_tenant

router = APIRouter()
tenant_service = TenantService()

@router.get("/", response_model=List[dict])
async def list_tenants():
    """List all available tenants"""
    tenants = tenant_service.list_tenants()
    return [
        {
            "tenant_id": tid,
            "company_name": tenant.company_name,
            "logo_url": tenant.logo_url,
            "primary_color": tenant.primary_color
        }
        for tid, tenant in tenants.items()
    ]

@router.get("/{tenant_id}", response_model=TenantSettings)
async def get_tenant(tenant_id: str):
    """Get tenant settings by ID"""
    tenant = tenant_service.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant

@router.post("/", response_model=TenantSettings)
async def create_tenant(tenant: TenantSettings):
    """Create a new tenant"""
    try:
        created_tenant = tenant_service.create_tenant(tenant)
        return created_tenant
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{tenant_id}", response_model=TenantSettings)
async def update_tenant(tenant_id: str, tenant_update: dict):
    """Update tenant settings"""
    updated_tenant = tenant_service.update_tenant(tenant_id, **tenant_update)
    if not updated_tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return updated_tenant

@router.delete("/{tenant_id}")
async def delete_tenant(tenant_id: str):
    """Delete a tenant"""
    if tenant_id == "default":
        raise HTTPException(status_code=400, detail="Cannot delete default tenant")
    
    success = tenant_service.delete_tenant(tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    return {"message": f"Tenant {tenant_id} deleted successfully"}

@router.get("/{tenant_id}/storage-paths")
async def get_tenant_storage_paths(tenant_id: str):
    """Get tenant-specific storage paths"""
    base_paths = ["data/uploads", "data/offers"]
    paths = {}
    
    for base_path in base_paths:
        tenant_path = tenant_service.get_tenant_storage_path(tenant_id, base_path)
        paths[base_path] = str(tenant_path)
    
    return {
        "tenant_id": tenant_id,
        "storage_paths": paths
    }

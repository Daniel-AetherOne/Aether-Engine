import json
import logging
from pathlib import Path
from typing import Dict, Optional
from app.models.tenant import TenantSettings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TenantService:
    """Service for managing tenant settings and configurations"""

    def __init__(self, config_file: str = "tenant_config.json"):
        self.config_file = Path(config_file)
        self._tenants: Dict[str, TenantSettings] = {}
        self._load_tenants()

    def _load_tenants(self):
        """Load tenant configurations from file or create defaults"""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for tenant_data in data.values():
                        tenant = TenantSettings(**tenant_data)
                        self._tenants[tenant.tenant_id] = tenant
                logger.info(f"Loaded {len(self._tenants)} tenants from config")
            except Exception as e:
                logger.error(f"Error loading tenant config: {e}")
                self._create_default_tenants()
        else:
            logger.info("No tenant config found, creating defaults")
            self._create_default_tenants()
            self._save_tenants()

    def _create_default_tenants(self):
        """Create default tenant configurations"""
        default_tenant = TenantSettings(
            tenant_id="default",
            company_name="Aether Engine",
            logo_url=None,
            hubspot_token=None,
            pipeline="Default Pipeline",
            stage="New Lead",
        )

        company_a = TenantSettings(
            tenant_id="company_a",
            company_name="Company A B.V.",
            logo_url="https://example.com/logo_a.png",
            hubspot_token="pat-company-a-token",
            pipeline="Company A Pipeline",
            stage="New Lead",
            primary_color="#dc2626",
            secondary_color="#991b1b",
        )

        company_b = TenantSettings(
            tenant_id="company_b",
            company_name="Company B Ltd.",
            logo_url="https://example.com/logo_b.png",
            hubspot_token="pat-company-b-token",
            pipeline="Company B Pipeline",
            stage="New Lead",
            primary_color="#059669",
            secondary_color="#047857",
        )

        self._tenants = {
            "default": default_tenant,
            "company_a": company_a,
            "company_b": company_b,
        }
        logger.info("Created default tenant configurations")

    def _save_tenants(self):
        """Save tenant configurations to file"""
        try:
            data = {tid: tenant.dict() for tid, tenant in self._tenants.items()}
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info("Saved tenant configurations to file")
        except Exception as e:
            logger.error(f"Error saving tenant config: {e}")

    def get_tenant(self, tenant_id: str) -> Optional[TenantSettings]:
        """Get tenant settings by ID"""
        if tenant_id not in self._tenants:
            logger.warning(f"Tenant {tenant_id} not found, falling back to default")
            # Fallback to default tenant
            return self._tenants.get("default")
        logger.info(f"Retrieved tenant settings for {tenant_id}")
        return self._tenants[tenant_id]

    def list_tenants(self) -> Dict[str, TenantSettings]:
        """List all available tenants"""
        return self._tenants.copy()

    def create_tenant(self, tenant: TenantSettings) -> TenantSettings:
        """Create a new tenant"""
        self._tenants[tenant.tenant_id] = tenant
        self._save_tenants()
        logger.info(f"Created new tenant: {tenant.tenant_id}")
        return tenant

    def update_tenant(self, tenant_id: str, **kwargs) -> Optional[TenantSettings]:
        """Update tenant settings"""
        if tenant_id not in self._tenants:
            logger.warning(f"Cannot update non-existent tenant: {tenant_id}")
            return None

        tenant = self._tenants[tenant_id]
        for key, value in kwargs.items():
            if hasattr(tenant, key):
                setattr(tenant, key, value)

        self._save_tenants()
        logger.info(f"Updated tenant: {tenant_id}")
        return tenant

    def delete_tenant(self, tenant_id: str) -> bool:
        """Delete a tenant (cannot delete default)"""
        if tenant_id == "default":
            logger.warning("Cannot delete default tenant")
            return False

        if tenant_id in self._tenants:
            del self._tenants[tenant_id]
            self._save_tenants()
            logger.info(f"Deleted tenant: {tenant_id}")
            return True
        return False

    def get_tenant_storage_path(self, tenant_id: str, base_path: str) -> Path:
        """Get tenant-specific storage path"""
        tenant_path = Path(base_path) / tenant_id
        logger.debug(f"Storage path for tenant {tenant_id}: {tenant_path}")
        return tenant_path

    def ensure_tenant_directories(self, tenant_id: str, base_paths: list[str]):
        """Ensure tenant-specific directories exist"""
        for base_path in base_paths:
            tenant_path = self.get_tenant_storage_path(tenant_id, base_path)
            tenant_path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory exists: {tenant_path}")

    def get_tenant_upload_path(self, tenant_id: str) -> Path:
        """Get tenant-specific upload path"""
        return self.get_tenant_storage_path(tenant_id, "data/uploads")

    def get_tenant_offers_path(self, tenant_id: str) -> Path:
        """Get tenant-specific offers path"""
        return self.get_tenant_storage_path(tenant_id, "data/offers")

    def log_tenant_activity(self, tenant_id: str, action: str, details: str = ""):
        """Log tenant-specific activity"""
        tenant = self.get_tenant(tenant_id)
        company_name = tenant.company_name if tenant else "Unknown"
        log_message = f"[TENANT:{tenant_id}:{company_name}] {action}"
        if details:
            log_message += f" - {details}"
        logger.info(log_message)

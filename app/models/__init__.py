# app/models/__init__.py
from app.models.lead import Lead, LeadFile  # noqa
from app.models.tenant import Tenant  # noqa
from app.models.tenant_settings import TenantSettings  # noqa
from app.models.user import User  # noqa

# (als je dit al had)
from app.models.upload_record import UploadRecord  # noqa  (alleen als die bestaat)

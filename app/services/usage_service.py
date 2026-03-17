from datetime import datetime

from sqlalchemy.orm import Session

from app.models.tenant_usage import TenantUsage


def get_or_create_usage(db: Session, tenant_id: str) -> TenantUsage:
    """
    Return the current monthly usage row for a tenant, creating it if needed.
    Uses UTC year/month for partitioning.
    """
    now = datetime.utcnow()
    year = now.year
    month = now.month

    usage = (
        db.query(TenantUsage)
        .filter(
            TenantUsage.tenant_id == tenant_id,
            TenantUsage.year == year,
            TenantUsage.month == month,
        )
        .first()
    )

    if usage is None:
        usage = TenantUsage(
            tenant_id=tenant_id,
            year=year,
            month=month,
            quotes_sent=0,
        )
        db.add(usage)
        db.commit()
        db.refresh(usage)

    return usage


def increment_usage(db: Session, tenant_id: str) -> TenantUsage:
    """
    Increment quotes_sent for the tenant's current monthly usage row.
    """
    usage = get_or_create_usage(db, tenant_id)
    usage.quotes_sent += 1

    db.add(usage)
    db.commit()
    db.refresh(usage)

    return usage


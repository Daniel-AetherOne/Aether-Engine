# scripts/bootstrap_dev_user.py
import uuid
from datetime import datetime, timezone

from app.db import SessionLocal
from app.models.user import User
from app.models.tenant import Tenant  # als je dit model hebt

TENANT_ID = "72f6a3d6-d81c-4af2-812e-1b4a870f6291"
EMAIL = "dev@paintly.local"
TIMEZONE = "America/Chicago"


def main():
    db = SessionLocal()
    try:
        # 1) tenant
        t = db.query(Tenant).filter(Tenant.id == TENANT_ID).first()
        if not t:
            t = Tenant(
                id=TENANT_ID, name="Dev Tenant"
            )  # pas velden aan op jouw Tenant model
            db.add(t)
            db.commit()

        # 2) user
        u = db.query(User).filter(User.email == EMAIL).first()
        if not u:
            u = User(
                id=str(uuid.uuid4()),
                tenant_id=TENANT_ID,
                email=EMAIL,
                password_hash="dev",  # jouw auth verwacht hashing; dit is alleen bootstrap
                timezone=TIMEZONE,
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
            db.add(u)
            db.commit()

        print("✅ tenant:", TENANT_ID)
        print("✅ user:", u.id, u.email, "tz:", u.timezone)

    finally:
        db.close()


if __name__ == "__main__":
    main()

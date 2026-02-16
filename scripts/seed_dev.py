from uuid import uuid4
from datetime import datetime, timezone

from app.db import SessionLocal
from app.models.lead import Lead


def main():
    db = SessionLocal()

    # pak de enige tenant_id uit DB (meest simpel)
    tenant_id = db.execute("select id from tenants limit 1").scalar()
    if not tenant_id:
        print("No tenant found. Create an account first via /auth/register.")
        return

    # maak 5 leads
    for i in range(5):
        lead = Lead(
            tenant_id=str(tenant_id),
            vertical="painters_us",
            name=f"Test Lead {i+1}",
            email=f"test{i+1}@example.com",
            phone="555-0100",
            notes="Interior painting, living room + hallway",
            status="NEW",
        )
        db.add(lead)

    db.commit()
    print("Seeded 5 leads for tenant:", tenant_id)


if __name__ == "__main__":
    main()

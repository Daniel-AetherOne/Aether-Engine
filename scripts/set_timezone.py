from app.db import SessionLocal
from app.models.user import User

TZ = "America/Chicago"  # kies je tenant tz


def main():
    db = SessionLocal()
    try:
        u = db.query(User).first()
        if not u:
            raise RuntimeError("No users found")
        u.timezone = TZ
        db.add(u)
        db.commit()
        print("✅ Set user timezone to:", TZ, "for user:", u.id, "tenant:", u.tenant_id)
    finally:
        db.close()


if __name__ == "__main__":
    main()

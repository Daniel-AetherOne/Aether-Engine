from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import create_engine

DATABASE_URL = "sqlite:///./levelai.db"  # zelfde als in alembic.ini

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # nodig voor SQLite met FastAPI threads
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

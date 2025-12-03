from datetime import datetime
from sqlalchemy.orm import Session
from app.models.quote import QuoteORM
from app.core.settings import settings


def get_quote_by_id(db: Session, quote_id: int) -> QuoteORM | None:
    return db.query(QuoteORM).filter(QuoteORM.id == quote_id).first()


def mark_quote_published(db: Session, quote_id: int, s3_key: str) -> QuoteORM:
    quote = db.query(QuoteORM).filter(QuoteORM.id == quote_id).first()
    if not quote:
        raise ValueError(f"Quote {quote_id} not found")

    quote.s3_key = s3_key
    quote.published_at = datetime.utcnow()

    # 👇 hier bouwen we de public URL
    quote.public_url = f"{settings.PUBLIC_BASE_URL}/public/quote/{quote.id}"

    db.commit()
    db.refresh(quote)
    return quote

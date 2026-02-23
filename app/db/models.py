from sqlalchemy import String, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from decimal import Decimal

class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String, primary_key=True)

    default_country: Mapped[str] = mapped_column(String(2), default="NL")
    default_timezone: Mapped[str] = mapped_column(String, default="Europe/Amsterdam")
    default_currency: Mapped[str] = mapped_column(String(3), default="EUR")

class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)

    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String, nullable=True)

    # intake
    square_meters: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
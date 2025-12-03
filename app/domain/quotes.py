from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any, Optional

from pydantic import BaseModel


class Quote(BaseModel):
    id: str
    owner_id: str

    lead: Any
    tenant: Any
    prediction: Any
    pricing: Any

    created_at: datetime
    validity_date: datetime

    # Optioneel: metadata voor publicatie
    s3_key: str | None = None
    latest_version_key: str | None = None

    @property
    def current_date_str(self) -> str:
        return self.created_at.strftime("%d-%m-%Y")

    @property
    def validity_date_str(self) -> str:
        return self.validity_date.strftime("%d-%m-%Y")


def _dummy_quote(quote_id: str) -> Quote:
    """Tijdelijke dummy-quote, zodat publish-flow werkt zonder DB."""

    lead = SimpleNamespace(
        name="Test Klant",
        email="test@example.com",
        phone="0612345678",
        address="Teststraat 1, 1234 AB Stad",
        square_meters=80,
    )

    tenant = SimpleNamespace(
        company_name="LevelAI Demo",
        primary_color="#2563eb",
        secondary_color="#64748b",
        logo_url=None,
    )

    prediction = SimpleNamespace(
        substrate="betonvloer",
        issues=["Haarscheuren", "Lichte oneffenheden"],
    )

    surcharges = [
        SimpleNamespace(description="Meerwerk trap", amount=10.0, total=800.0),
    ]

    pricing = SimpleNamespace(
        base_per_m2=25.0,
        subtotal=2000.0,
        surcharges=surcharges,
        vat_amount=588.0,
        total=2588.0,
        doorlooptijd="Uitvoering binnen 2 weken na akkoord",
        aannames=[
            "Ruimte is leeg en goed bereikbaar",
            "Stroom en water zijn aanwezig",
        ],
    )

    now = datetime.utcnow()
    validity = now + timedelta(days=30)

    return Quote(
        id=quote_id,
        owner_id="debug-user",
        lead=lead,
        tenant=tenant,
        prediction=prediction,
        pricing=pricing,
        created_at=now,
        validity_date=validity,
        s3_key=None,
        latest_version_key=None,
    )


def get_quote_for_publish(quote_id: str) -> Optional[Quote]:
    """Later vervangen door echte DB-call. Nu altijd dummy-quote."""
    return _dummy_quote(quote_id)


def mark_quote_published(
    quote_id: str,
    s3_key: str,
    version_key: str | None = None,
) -> None:
    # TODO: later in DB opslaan dat deze quote is gepubliceerd + versie
    print(f"[quotes] Mark quote {quote_id} published at {s3_key}")
    if version_key:
        print(f"[quotes]   version stored at {version_key}")


def mark_quote_unpublished(quote_id: str) -> None:
    # TODO: later in DB bijhouden dat deze quote niet meer gepubliceerd is
    print(f"[quotes] Mark quote {quote_id} UNPUBLISHED")

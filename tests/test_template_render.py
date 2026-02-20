from types import SimpleNamespace
from app.templates import render_template

# Dummy data voor de template
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

context = {
    "lead": lead,
    "tenant": tenant,
    "prediction": prediction,
    "pricing": pricing,
    "quote_id": "Q-TEST-001",
    "current_date": "21-11-2025",
    "validity_date": "21-12-2025",
}

html = render_template("quote.html", context)

print(html)

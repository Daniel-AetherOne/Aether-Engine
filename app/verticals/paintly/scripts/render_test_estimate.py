from pathlib import Path
from app.verticals.paintly.render_estimate import render_us_estimate_html

vision = {
    "surfaces": [
        {
            "label": "Living room walls",
            "area_sqft": 450,
            "prep_level": "Light",
            "access": "Standard",
        }
    ]
}

pricing = {
    "pricing_ready": True,
    "labor_usd": 1200,
    "materials_usd": 350,
    "total_usd": 1550,
}

project = {"lead_id": "TEST123", "location": "Austin, TX"}
company = {
    "name": "Paintly",
    "phone": "(555) 123-4567",
    "email": "hello@getpaintly.com",
}

html = render_us_estimate_html(
    vision_output=vision,
    pricing_output=pricing,
    project=project,
    company=company,
)

out = Path("test_estimate.html")
out.write_text(html, encoding="utf-8")
print(f"Wrote {out.resolve()}")

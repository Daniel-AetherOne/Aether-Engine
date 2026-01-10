from pathlib import Path
from app.verticals.painters_us.render_estimate import render_us_estimate_html

BAD_STRINGS_ALWAYS = [
    "vision output",
    "placeholder",
]

BAD_STRINGS_IF_READY = [
    "TBD",
]


def run(pricing_ready: bool) -> str:
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
        "pricing_ready": pricing_ready,
        "labor_usd": 1200,
        "materials_usd": 350,
        "total_usd": 1550,
    }

    project = {
        "lead_id": "TEST123",
        "location": "Austin, TX",
    }

    company = {
        "name": "Paintly",
        "phone": "(555) 123-4567",
        "email": "hello@getpaintly.com",
    }

    return render_us_estimate_html(
        vision_output=vision,
        pricing_output=pricing,
        project=project,
        company=company,
    )


def assert_sendable(html: str, pricing_ready: bool) -> None:
    for s in BAD_STRINGS_ALWAYS:
        if s.lower() in html.lower():
            raise SystemExit(f"FAIL: forbidden string found: {s}")

    if pricing_ready:
        for s in BAD_STRINGS_IF_READY:
            if s.lower() in html.lower():
                raise SystemExit(f"FAIL: pricing_ready=True but found: {s}")

    if pricing_ready and "$" not in html:
        raise SystemExit("FAIL: pricing_ready=True but no currency symbol found")


if __name__ == "__main__":
    html = run(pricing_ready=True)
    assert_sendable(html, pricing_ready=True)

    out = Path("test_estimate_sendable.html")
    out.write_text(html, encoding="utf-8")
    print(f"PASS: sendability check OK → wrote {out.resolve()}")

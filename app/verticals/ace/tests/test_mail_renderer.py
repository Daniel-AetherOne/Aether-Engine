from app.verticals.ace.explain.mail_renderer import render_approval_email


def test_render_approval_email_contains_steps():
    out = {
        "status": "OK",
        "currency": "EUR",
        "total": {"amount": "100.00", "currency": "EUR"},
        "warnings": [{"code": "APPROVAL_REQUIRED", "message": "Manual approval needed", "meta": {}}],
        "blocks": [],
        "lines": [
            {
                "line_id": "l1",
                "sku": "SKU1",
                "qty": 3,
                "net_sell": {"amount": "100.00", "currency": "EUR"},
                "steps": ["Netto inkoop: ...", "Minimummarge: OK"],
            }
        ],
    }

    subject, body = render_approval_email(out)
    assert "APPROVAL" in subject
    assert "WARNINGS" in body
    assert "• Netto inkoop" in body
    assert "• Minimummarge" in body

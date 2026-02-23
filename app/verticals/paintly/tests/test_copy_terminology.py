# app/verticals/painters_us/tests/test_copy_terminology.py

from app.verticals.paintly.copy import assert_no_forbidden_terms


def test_us_estimate_has_no_forbidden_terms(rendered_html: str):
    """
    Ensures US Painters estimate output never contains
    forbidden terminology like 'quote', 'proposal', 'VAT', etc.
    """
    assert_no_forbidden_terms(rendered_html)

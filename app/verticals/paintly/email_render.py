# app/verticals/painters_us/email_render.py
from __future__ import annotations

from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_estimate_ready_email(*, customer_name: str, quote_url: str, company_name: str) -> str:
    tmpl = _env.get_template("email/estimate_ready.html")
    return tmpl.render(
        customer_name=customer_name,
        quote_url=quote_url,
        company_name=company_name,
    )


def render_estimate_accepted_email(*, customer_name: str, quote_url: str, company_name: str) -> str:
    tmpl = _env.get_template("email/estimate_accepted.html")
    return tmpl.render(
        customer_name=customer_name,
        quote_url=quote_url,
        company_name=company_name,
    )


def render_painter_estimate_accepted_email(
    *,
    company_name: str,
    lead_name: str,
    lead_email: str,
    lead_phone: str,
    project_description: str,
    square_meters: str,
    job_type: str,
    price_display: str,
    quote_url: str,
    admin_url: str,
) -> str:
    tmpl = _env.get_template("email/painter_estimate_accepted.html")
    return tmpl.render(
        company_name=company_name,
        lead_name=lead_name,
        lead_email=lead_email,
        lead_phone=lead_phone,
        project_description=project_description,
        square_meters=square_meters,
        job_type=job_type,
        price_display=price_display,
        quote_url=quote_url,
        admin_url=admin_url,
    )

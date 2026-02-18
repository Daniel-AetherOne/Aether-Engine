# app/verticals/painters_us/email_render.py
from __future__ import annotations

from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

def render_estimate_ready_email(*, customer_name: str, public_url: str, company_name: str) -> str:
    tmpl = _env.get_template("email/estimate_ready.html")
    return tmpl.render(customer_name=customer_name, public_url=public_url, company_name=company_name)


def render_estimate_accepted_email(*, customer_name: str, public_url: str, company_name: str) -> str:
    tmpl = _env.get_template("email/estimate_accepted.html")
    return tmpl.render(customer_name=customer_name, public_url=public_url, company_name=company_name)

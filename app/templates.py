from pathlib import Path
from typing import Mapping, Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

# Ga uit van structuur:
# project_root/
#   app/
#     templates.py  (dit bestand)
#   templates/
#     quote.html

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def render_template(name: str, context: Mapping[str, Any]) -> str:
    """
    Render een Jinja2-template naar een HTML-string.

    Voorbeeld:
        html = render_template("quote.html", {"quote": quote})
    """
    template = _env.get_template(name)
    return template.render(**context)

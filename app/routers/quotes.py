# app/routers/quotes.py
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Lead
from app.core.settings import settings

router = APIRouter(prefix="/quotes", tags=["quotes"])

# Dit is platform/admin UI. Mag in core/templates of app/templates zolang je dit expliciet “platform” noemt.
templates = Jinja2Templates(directory="app/templates")


def _public_base_url() -> str:
    raw = (getattr(settings, "CLOUDFRONT_DOMAIN", None) or "").strip()
    if raw:
        return (
            raw.rstrip("/")
            if raw.startswith("http")
            else ("https://" + raw.rstrip("/"))
        )
    # fallback S3 (pas aan als je settings keys anders heten)
    return f"https://{settings.S3_BUCKET}.s3.amazonaws.com"


@router.get("/dashboard", response_class=HTMLResponse)
def quotes_dashboard(request: Request, db: Session = Depends(get_db)):
    leads = db.query(Lead).order_by(Lead.id.desc()).limit(50).all()
    return templates.TemplateResponse(
        "quotes_dashboard.html",
        {"request": request, "leads": leads, "public_base": _public_base_url()},
    )

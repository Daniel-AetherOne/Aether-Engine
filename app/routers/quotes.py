# app/routers/quotes.py
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from sqlalchemy.orm import Session
import boto3

from app.db import get_db
from app.models import Lead, LeadFile
from app.schemas.intake import IntakePayload
from app.services.pricing_engine import calculate_quote
from app.core.settings import settings
from app.services.email_service import send_quote_email

router = APIRouter(prefix="/quotes", tags=["quotes"])
templates = Jinja2Templates(directory="app/templates")


def get_s3_client():
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
    )


def _get_cloudfront_base_url() -> str:
    """
    Bouw een nette base URL voor CloudFront.

    Werkt met:
    - CLOUDFRONT_DOMAIN="d1bjdnx9r99951.cloudfront.net"
    - of CLOUDFRONT_DOMAIN="https://d1bjdnx9r99951.cloudfront.net"
    """
    raw = (getattr(settings, "CLOUDFRONT_DOMAIN", None) or "").strip()
    if not raw:
        raise HTTPException(
            status_code=500, detail="CLOUDFRONT_DOMAIN is niet ingesteld"
        )

    if raw.startswith("http://") or raw.startswith("https://"):
        return raw.rstrip("/")
    return "https://" + raw.rstrip("/")


def _s3_base_url() -> str:
    """
    Virtual-hosted style S3 URL.
    """
    return f"https://{settings.S3_BUCKET}.s3.{settings.S3_REGION}.amazonaws.com"


def _public_base_url() -> str:
    """
    Kies base URL voor publieke assets:
    - CloudFront als aanwezig
    - anders directe S3 base URL
    """
    if getattr(settings, "CLOUDFRONT_DOMAIN", None):
        return _get_cloudfront_base_url()
    return _s3_base_url()


@router.post("/publish/{lead_id}")
def publish_quote(
    lead_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Publiceer een offerte als HTML op S3 (+ evt CloudFront)
    en stuur optioneel een e-mail naar de klant.
    """
    # 1) Lead ophalen
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead niet gevonden")

    # Eventuele bestanden ophalen (voor foto's in de offerte)
    files = db.query(LeadFile).filter(LeadFile.lead_id == lead_id).all()

    # 2) IntakePayload reconstrueren (minimaal wat de price engine nodig heeft)
    payload_data = {
        "tenant_id": getattr(lead, "tenant_id", None),
        "name": lead.name,
        "email": lead.email,
        "phone": lead.phone,
        "project_description": lead.notes,
        "square_meters": getattr(lead, "square_meters", None),
        "object_keys": [f.s3_key for f in files],
    }

    try:
        payload = IntakePayload(**payload_data)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Kan payload niet opbouwen voor quote: {e}",
        )

    # 3) Quote berekenen
    quote = calculate_quote(payload, lead)

    # 4) HTML renderen via Jinja template
    template = templates.get_template("quote.html")

    # Base URL voor images/assets in de offerte
    public_base = _public_base_url()
    file_base_url = public_base + "/"  # voor foto's, bv. {base}/uploads/...

    html = template.render(
        lead=lead,
        quote=quote,
        files=files,
        file_base_url=file_base_url,
        tenant_id=getattr(lead, "tenant_id", None),
    )

    # 5) Uploaden naar S3 (publiek voor stap 8.2)
    s3 = get_s3_client()

    # Checklist-friendly key:
    key = f"quotes/{lead_id}/quote.html"

    try:
        s3.put_object(
            Bucket=settings.S3_BUCKET,
            Key=key,
            Body=html.encode("utf-8"),
            ContentType="text/html; charset=utf-8",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Upload naar S3 mislukt: {e}",
        )

    # 6) Public URL bouwen (CloudFront als aanwezig, anders S3)
    public_url = f"{public_base}/{key}"

    # 7) E-mail versturen als background task (kan falen zonder de response te breken)
    # Als je dit tijdelijk wil uitzetten: comment deze block.
    if getattr(lead, "email", None):
        background_tasks.add_task(
            send_quote_email,
            to_email=lead.email,
            to_name=getattr(lead, "name", "") or "",
            public_url=public_url,
            lead_id=lead.id,
        )

    return {
        "lead_id": lead_id,
        "key": key,
        "public_url": public_url,
        "via": "cloudfront" if getattr(settings, "CLOUDFRONT_DOMAIN", None) else "s3",
    }


@router.get("/dashboard", response_class=HTMLResponse)
def quotes_dashboard(request: Request, db: Session = Depends(get_db)):
    """
    Simpel intern dashboard met leads + link naar offerte (public_url).
    Werkt ook zonder CloudFront.
    """
    leads = db.query(Lead).order_by(Lead.id.desc()).limit(50).all()

    public_base = _public_base_url()

    return templates.TemplateResponse(
        "quotes_dashboard.html",
        {
            "request": request,
            "leads": leads,
            "public_base": public_base,
        },
    )

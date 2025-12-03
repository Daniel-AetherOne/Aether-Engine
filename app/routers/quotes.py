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
    """
    S3 client die regio uit settings gebruikt.
    Credentials haalt boto3 uit ~/.aws/credentials.
    """
    return boto3.client(
        "s3",
        region_name=settings.S3_REGION,
    )


def _get_cloudfront_base_url() -> str:
    """
    Bouw een nette base URL voor CloudFront.

    Werkt met:
    - CLOUDFRONT_DOMAIN="d1bjdnx9r99951.cloudfront.net"
    - of CLOUDFRONT_DOMAIN="https://d1bjdnx9r99951.cloudfront.net"
    """
    raw = (settings.CLOUDFRONT_DOMAIN or "").strip()
    if not raw:
        raise HTTPException(
            status_code=500, detail="CLOUDFRONT_DOMAIN is niet ingesteld"
        )

    if raw.startswith("http://") or raw.startswith("https://"):
        base = raw.rstrip("/")
    else:
        base = "https://" + raw.rstrip("/")

    return base  # bv. "https://d1bjdnx9r99951.cloudfront.net"


@router.post("/publish/{lead_id}")
def publish_quote(
    lead_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Publiceer een offerte als HTML op S3 + CloudFront
    én stuur automatisch een e-mail naar de klant.
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

    cloudfront_base = _get_cloudfront_base_url()
    file_base_url = cloudfront_base + "/"  # voor foto's

    html = template.render(
        lead=lead,
        quote=quote,
        files=files,
        file_base_url=file_base_url,
        tenant_id=getattr(lead, "tenant_id", None),
    )

    # 5) Uploaden naar S3
    s3 = get_s3_client()
    key = f"quotes/{lead_id}/index.html"

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

    # 6) Public URL bouwen
    public_url = f"{cloudfront_base}/{key}"

    # 7) E-mail versturen als background task
    background_tasks.add_task(
        send_quote_email,
        to_email=lead.email,
        to_name=lead.name,
        public_url=public_url,
        lead_id=lead.id,
    )

    return {
        "lead_id": lead_id,
        "public_url": public_url,
    }


@router.get("/dashboard", response_class=HTMLResponse)
def quotes_dashboard(request: Request, db: Session = Depends(get_db)):
    """
    Simpel intern dashboard met leads + link naar offerte (public_url).
    """
    leads = db.query(Lead).order_by(Lead.id.desc()).limit(50).all()

    cloudfront_base = _get_cloudfront_base_url()

    return templates.TemplateResponse(
        "quotes_dashboard.html",
        {
            "request": request,
            "leads": leads,
            "cloudfront_base": cloudfront_base,
        },
    )

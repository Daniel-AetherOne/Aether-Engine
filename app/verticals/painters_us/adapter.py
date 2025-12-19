from __future__ import annotations

from fastapi.templating import Jinja2Templates
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.tasks.vision_task import run_vision_for_lead

from app.core.contracts import IntakeResult
from app.schemas.intake import IntakePayload
from app.models import Lead, LeadFile

painters_us_templates = Jinja2Templates(directory="app/verticals/painters_us/templates")


class PaintersUSAdapter:
    vertical_id = "painters_us"

    def render_intake_form(self, request, lead_id: str):
        return painters_us_templates.TemplateResponse(
            "intake_form_us.html",
            {
                "request": request,
                "lead_id": lead_id,
                "tenant_id": "painters_us",
                "vertical": "painters_us",
            },
        )

    def run_vision(self, db, lead_id: int) -> dict:
        """
        Run vision pipeline for a painters_us lead.
        """
        return run_vision_for_lead(db, lead_id)

    async def create_lead_from_form(self, request, db: Session) -> IntakeResult:
        form = await request.form()
        form_dict = dict(form)

        # Units support: sqft → m² (als je dit later in vertical intake wil opsplitsen is dit al netjes)
        area_unit = form_dict.get("area_unit") or "m2"
        raw_area = form_dict.get("square_meters")

        square_meters = None
        if raw_area:
            try:
                val = float(raw_area)
                square_meters = val * 0.092903 if area_unit == "sqft" else val
            except ValueError:
                square_meters = None

        photo_keys = form.getlist("photo_keys") if hasattr(form, "getlist") else []

        payload_data = {
            "tenant_id": form_dict.get("tenant_id") or "painters_us",
            "name": form_dict.get("name"),
            "email": form_dict.get("email"),
            "phone": form_dict.get("phone"),
            "project_description": form_dict.get("address"),
            "object_keys": photo_keys,
            "square_meters": square_meters,
        }

        try:
            payload = IntakePayload(**payload_data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid intake payload: {e}")

        tenant_id = payload.tenant_id or "painters_us"
        vertical = self.vertical_id

        # 1) Create Lead
        lead = Lead(
            tenant_id=tenant_id,
            name=payload.name,
            email=payload.email,
            phone=payload.phone,
            notes=payload.project_description,
        )
        lead.vertical = vertical

        db.add(lead)
        db.commit()
        db.refresh(lead)

        # 2) Save uploads
        saved_keys: list[str] = []
        object_keys = list(dict.fromkeys(payload.object_keys or []))  # dedupe
        for key in object_keys:
            db.add(
                LeadFile(
                    lead_id=lead.id,
                    s3_key=key,
                    size_bytes=0,
                    content_type="image/*",
                )
            )
            saved_keys.append(key)
        db.commit()

        return IntakeResult(
            lead_id=str(lead.id),
            tenant_id=lead.tenant_id,
            vertical=lead.vertical,
            files=saved_keys,
        )

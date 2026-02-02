from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.contracts import IntakeResult
from app.core.settings import settings
from app.models import Lead, LeadFile
from app.schemas.intake import IntakePayload
from app.tasks.vision_task import run_vision_for_lead
from aether.engine.facade import compute_quote_for_lead_v15

painters_us_templates = Jinja2Templates(directory="app/verticals/painters_us/templates")


def _strip_tenant_prefix(tenant_id: str, key: str) -> str:
    key = (key or "").strip()
    if not key:
        return ""
    prefix = f"{tenant_id}/"
    return key[len(prefix) :] if key.startswith(prefix) else key


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

    def run_vision(self, db: Session, lead_id: int) -> dict:
        return run_vision_for_lead(db, lead_id)

    def compute_quote(self, db: Session, lead_id: int) -> Dict[str, Any]:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        if not lead.vertical:
            lead.vertical = self.vertical_id
            db.add(lead)
            db.commit()
            db.refresh(lead)

        if lead.vertical != self.vertical_id:
            raise HTTPException(
                status_code=400,
                detail=f"Lead vertical mismatch: {lead.vertical} (expected {self.vertical_id})",
            )

        files = db.query(LeadFile).filter(LeadFile.lead_id == lead_id).all()
        if not files:
            raise HTTPException(status_code=400, detail="No uploads for lead")

        try:
            # ✅ Run engine facade (config-driven)
            result = compute_quote_for_lead_v15(db, lead, vertical_id=self.vertical_id)

            html_key = result.get("estimate_html_key")
            if not html_key:
                raise RuntimeError(
                    "engine_missing_estimate_html_key "
                    f"(status={result.get('engine_status')}, "
                    f"failure_step={result.get('failure_step')}, "
                    f"available_steps={result.get('available_steps')}, "
                    f"logs_tail={result.get('logs_tail')})"
                )

            estimate_obj = result.get("estimate_json")

            # persist estimate_json as string in DB (existing behavior)
            if isinstance(estimate_obj, str):
                try:
                    parsed = json.loads(estimate_obj)
                except Exception:
                    lead.estimate_json = estimate_obj
                else:
                    lead.estimate_json = json.dumps(
                        jsonable_encoder(parsed), ensure_ascii=False
                    )
            else:
                lead.estimate_json = json.dumps(
                    estimate_obj, ensure_ascii=False, default=str
                )

            lead.estimate_html_key = html_key

            needs_review = bool(result.get("needs_review", False))
            lead.status = "NEEDS_REVIEW" if needs_review else "SUCCEEDED"

            db.add(lead)
            db.commit()
            db.refresh(lead)

            return {
                "estimate_json": lead.estimate_json,
                "estimate_html_key": lead.estimate_html_key,
                "needs_review": needs_review,
            }

        except HTTPException:
            raise
        except Exception as e:
            # mark failed and surface a clear error in the UI
            lead.status = "FAILED"
            db.add(lead)
            db.commit()

            raise HTTPException(
                status_code=500,
                detail=f"compute_quote_failed:{type(e).__name__}:{e}",
            )

    async def create_lead_from_form(self, request, db: Session) -> IntakeResult:
        form = await request.form()
        form_dict = dict(form)

        tenant_id = (
            form_dict.get("tenant_id") or "painters_us"
        ).strip() or "painters_us"

        # photo keys komen van hidden inputs (object_key uit presign)
        photo_keys = form.getlist("photo_keys") if hasattr(form, "getlist") else []
        # dedupe + normalize => tenant-loos opslaan in DB
        object_keys = []
        seen = set()
        for k in photo_keys:
            k2 = _strip_tenant_prefix(tenant_id, str(k))
            if k2 and k2 not in seen:
                seen.add(k2)
                object_keys.append(k2)

        # FASE 3 safety: max uploads
        if len(object_keys) > settings.UPLOAD_MAX_FILES:
            raise HTTPException(
                status_code=400,
                detail=f"too_many_files:max={settings.UPLOAD_MAX_FILES}",
            )

        # Units support: sqft → m²
        area_unit = (form_dict.get("area_unit") or "m2").strip()
        raw_area = form_dict.get("square_meters")

        square_meters = None
        if raw_area:
            try:
                val = float(raw_area)
                square_meters = val * 0.092903 if area_unit == "sqft" else val
            except ValueError:
                square_meters = None

        payload_data = {
            "tenant_id": tenant_id,
            "name": form_dict.get("name"),
            "email": form_dict.get("email"),
            "phone": form_dict.get("phone"),
            "project_description": form_dict.get("project_description")
            or form_dict.get("address"),
            "object_keys": object_keys,  # ✅ tenant-loos
            "square_meters": square_meters,
        }

        try:
            payload = IntakePayload(**payload_data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid intake payload: {e}")

        # 1) Create Lead
        lead = Lead(
            tenant_id=tenant_id,
            name=payload.name,
            email=payload.email,
            phone=payload.phone,
            status="NEW",
        )
        lead.vertical = self.vertical_id
        lead.intake_payload = json.dumps(payload_data, ensure_ascii=False)

        if hasattr(lead, "notes"):
            lead.notes = payload_data.get("project_description") or None

        db.add(lead)
        db.commit()
        db.refresh(lead)

        # 2) Save uploads
        saved_keys: list[str] = []
        for key in object_keys:
            db.add(
                LeadFile(
                    lead_id=lead.id,
                    s3_key=key,  # ✅ tenant-loos in DB
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

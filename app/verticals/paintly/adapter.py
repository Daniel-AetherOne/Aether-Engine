from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Set

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.contracts import VerticalAdapter, IntakeResult
from app.core.settings import settings
from app.models import Lead, LeadFile
from app.schemas.intake import IntakePayload
from app.tasks.vision_task import run_vision_for_lead
from aether.engine.facade import compute_quote_for_lead_v15
from app.verticals.paintly.eu_config import resolve_eu_config

paintly_templates = Jinja2Templates(directory="app/verticals/paintly/templates")
logger = logging.getLogger(__name__)


def _strip_tenant_prefix(tenant_id: str, key: str) -> str:
    """
    Sommige upload flows prefixen keys met '{tenant_id}/...'.
    In DB slaan we tenant-loos op, dus strippen we dat hier.
    Als er geen prefix is: no-op.
    """
    key = (key or "").strip()
    if not key:
        return ""
    prefix = f"{tenant_id}/"
    return key[len(prefix) :] if key.startswith(prefix) else key


def _extract_object_keys_from_form(form: Any, tenant_id: str) -> List[str]:
    """
    - Leest photo_keys[] uit form
    - Dedupe
    - Stript eventueel tenant prefix
    - Retourneert tenant-loze object_keys
    """
    photo_keys = form.getlist("photo_keys") if hasattr(form, "getlist") else []
    object_keys: List[str] = []
    seen: Set[str] = set()

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

    return object_keys


def _parse_square_meters(form_dict: dict) -> float | None:
    """
    Support:
      - area_unit=sqm/m2  -> square_meters as-is
      - area_unit=sqft    -> convert to m2
    """
    area_unit = (form_dict.get("area_unit") or "m2").strip().lower()
    raw_area = form_dict.get("square_meters")

    if not raw_area:
        return None

    try:
        val = float(raw_area)
    except ValueError:
        return None

    if area_unit in {"sqft", "ft2", "ft²"}:
        return val * 0.092903

    # default m2/sqm
    return val


def _resolve_eu_cfg_from_form(form_dict: dict, payload_data: dict) -> dict:
    """
    Self-contained EU config resolver. Never relies on outer scope.
    """
    country = (
        (form_dict.get("country") or payload_data.get("country") or "NL")
        .strip()
        .upper()
    )
    return resolve_eu_config(country)


class PaintlyAdapter(VerticalAdapter):
    vertical_id = "paintly"

    def render_intake_form(self, request, lead_id: str, tenant_id: str = "public"):
        return paintly_templates.TemplateResponse(
            "intake_form_nl.html",
            {
                "request": request,
                "lead_id": lead_id,
                "tenant_id": tenant_id,
                "vertical": self.vertical_id,
            },
        )

    def run_vision(self, db: Session, lead_id: int) -> dict:
        return run_vision_for_lead(db, lead_id)

    def compute_quote(self, db: Session, lead_id: int) -> Dict[str, Any]:
        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # Ensure vertical
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

        # Must have uploads
        files = db.query(LeadFile).filter(LeadFile.lead_id == lead_id).all()
        if not files:
            raise HTTPException(status_code=400, detail="No uploads for lead")

        try:
            # ✅ Run engine facade (config-driven)
            result = compute_quote_for_lead_v15(db, lead, vertical_id=self.vertical_id)

            # DEBUG (safe, non-blocking)
            try:
                import hashlib

                dbg_logger = logging.getLogger("aether")
                dbg_logger.warning(
                    "DEBUG facade estimate_html_key=%s",
                    result.get("estimate_html_key"),
                )

                est_dbg = result.get("estimate_json")
                if isinstance(est_dbg, str):
                    try:
                        est_dbg_obj = json.loads(est_dbg)
                    except Exception:
                        est_dbg_obj = {"_raw": est_dbg}
                elif isinstance(est_dbg, dict):
                    est_dbg_obj = est_dbg
                else:
                    est_dbg_obj = {"_type": str(type(est_dbg))}

                digest = hashlib.md5(
                    json.dumps(est_dbg_obj, sort_keys=True, default=str).encode("utf-8")
                ).hexdigest()
                dbg_logger.warning("DEBUG facade estimate_json_md5=%s", digest)
            except Exception:
                pass

            html_key = result.get("estimate_html_key")
            if not html_key:
                raise RuntimeError("engine_missing_estimate_html_key")

            estimate_obj = result.get("estimate_json")

            # Persist estimate_json as string
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
                    jsonable_encoder(estimate_obj),
                    ensure_ascii=False,
                    default=str,
                )

            lead.estimate_html_key = html_key

            needs_review = bool(result.get("needs_review", False))
            lead.status = "NEEDS_REVIEW" if needs_review else "SUCCEEDED"

            lead.error_message = None
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
            lead.status = "FAILED"
            lead.error_message = f"{type(e).__name__}: {e}"
            db.add(lead)
            db.commit()
            raise HTTPException(
                status_code=500,
                detail=f"compute_quote_failed:{type(e).__name__}:{e}",
            )

    async def upsert_lead_from_form(
        self,
        request,
        db: Session,
        tenant_id: str,
    ) -> IntakeResult:
        """
        Optie B:
        - Als form een lead_id bevat: update bestaande lead + sync uploads (LeadFile) -> GEEN nieuwe lead.
        - Als geen lead_id: fallback naar create_lead_from_form (legacy create).
        """
        form = await request.form()
        form_dict = dict(form)

        # ✅ Tenant komt van auth/router, NIET van form
        tenant_id = (tenant_id or "").strip() or "public"

        raw_lead_id = (form_dict.get("lead_id") or "").strip()
        lead_id_int: int | None = None
        if raw_lead_id:
            try:
                lead_id_int = int(raw_lead_id)
            except Exception:
                raise HTTPException(status_code=400, detail="invalid_lead_id")

        # object_keys uit form (tenant-loos)
        object_keys = _extract_object_keys_from_form(form, tenant_id=tenant_id)

        square_meters = _parse_square_meters(form_dict)

        payload_data = {
            "tenant_id": tenant_id,
            "name": form_dict.get("name"),
            "email": form_dict.get("email"),
            "phone": form_dict.get("phone"),
            "project_description": form_dict.get("project_description")
            or form_dict.get("address"),
            "object_keys": object_keys,  # ✅ tenant-loos
            "square_meters": square_meters,
            "job_type": form_dict.get("job_type"),
        }

        try:
            _ = IntakePayload(**payload_data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid intake payload: {e}")

        # CASE A: geen lead_id => create
        if lead_id_int is None:
            return await self.create_lead_from_form(request, db, tenant_id=tenant_id)

        # CASE B: lead_id => update bestaande lead (tenant-scoped!)
        lead = (
            db.query(Lead)
            .filter(Lead.id == lead_id_int)
            .filter(Lead.tenant_id == tenant_id)
            .first()
        )
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # Ensure vertical correct
        if not lead.vertical:
            lead.vertical = self.vertical_id

        if lead.vertical != self.vertical_id:
            raise HTTPException(
                status_code=400,
                detail=f"Lead vertical mismatch: {lead.vertical} (expected {self.vertical_id})",
            )

        # ✅ EU config toevoegen aan payload (self-contained)
        eu_cfg = _resolve_eu_cfg_from_form(form_dict, payload_data)
        payload_data["country"] = eu_cfg["country"]
        payload_data["vat_rate"] = eu_cfg["vat_rate"]
        payload_data["currency"] = eu_cfg["currency"]
        payload_data["timezone"] = eu_cfg["timezone"]

        # Update lead fields
        lead.name = payload_data.get("name")
        lead.email = payload_data.get("email")
        lead.phone = payload_data.get("phone")
        lead.intake_payload = json.dumps(payload_data, ensure_ascii=False)

        if hasattr(lead, "notes"):
            lead.notes = payload_data.get("project_description") or None

        if not getattr(lead, "status", None):
            lead.status = "NEW"

        db.add(lead)
        db.commit()
        db.refresh(lead)

        # Sync LeadFile rows to match object_keys (idempotent)
        existing = db.query(LeadFile).filter(LeadFile.lead_id == lead.id).all()
        existing_keys = {lf.s3_key for lf in existing if isinstance(lf.s3_key, str)}

        # Add missing
        for key in object_keys:
            if key not in existing_keys:
                db.add(
                    LeadFile(
                        lead_id=lead.id,
                        s3_key=key,
                        size_bytes=0,
                        content_type="image/*",
                    )
                )

        # Optional: remove extras not present anymore
        desired = set(object_keys)
        for lf in existing:
            if lf.s3_key and lf.s3_key not in desired:
                db.delete(lf)

        db.commit()

        return IntakeResult(
            lead_id=str(lead.id),
            tenant_id=lead.tenant_id,
            vertical=lead.vertical,
            files=object_keys,
        )

    async def create_lead_from_form(
        self,
        request,
        db: Session,
        tenant_id: str,
    ) -> IntakeResult:
        form = await request.form()
        form_dict = dict(form)

        # ✅ Tenant komt van auth/router, NIET van form
        tenant_id = (tenant_id or "").strip() or "public"

        object_keys = _extract_object_keys_from_form(form, tenant_id=tenant_id)
        square_meters = _parse_square_meters(form_dict)

        payload_data = {
            "tenant_id": tenant_id,
            "name": form_dict.get("name"),
            "email": form_dict.get("email"),
            "phone": form_dict.get("phone"),
            "project_description": form_dict.get("project_description")
            or form_dict.get("address"),
            "object_keys": object_keys,  # ✅ tenant-loos
            "square_meters": square_meters,
            "job_type": form_dict.get("job_type"),
        }

        try:
            payload = IntakePayload(**payload_data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid intake payload: {e}")

        # ✅ EU config toevoegen aan payload (self-contained)
        eu_cfg = _resolve_eu_cfg_from_form(form_dict, payload_data)
        payload_data["country"] = eu_cfg["country"]
        payload_data["vat_rate"] = eu_cfg["vat_rate"]
        payload_data["currency"] = eu_cfg["currency"]
        payload_data["timezone"] = eu_cfg["timezone"]

        # 1) Create Lead
        lead = Lead(
            tenant_id=tenant_id,
            vertical=self.vertical_id,
            name=payload.name,
            email=payload.email,
            phone=payload.phone,
            status="NEW",
        )
        lead.intake_payload = json.dumps(payload_data, ensure_ascii=False)

        if hasattr(lead, "notes"):
            lead.notes = payload_data.get("project_description") or None

        db.add(lead)
        db.commit()
        db.refresh(lead)

        # 2) Save uploads
        saved_keys: List[str] = []
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

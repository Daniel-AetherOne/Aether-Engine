# app/services/lead_store.py
from __future__ import annotations
from pathlib import Path
import json
from typing import Optional
from datetime import datetime

from app.models.lead import Lead  # jouw bestaande Lead model

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "leads"
DATA_DIR.mkdir(parents=True, exist_ok=True)

class LeadStore:
    @staticmethod
    def _path(lead_id: str) -> Path:
        return DATA_DIR / f"{lead_id}.json"

    @classmethod
    def upsert(cls, lead: Lead) -> Lead:
        path = cls._path(lead.lead_id)
        # update timestamp indien aanwezig
        try:
            d = lead.model_dump()
            if "submission_date" in d:
                # niets; jouw model heeft al submission_date
                pass
            else:
                d["submission_date"] = datetime.utcnow().isoformat()
        except Exception:
            pass

        with path.open("w", encoding="utf-8") as f:
            json.dump(lead.model_dump(), f, ensure_ascii=False, indent=2, default=str)
        return lead

    @classmethod
    def get(cls, lead_id: str) -> Optional[Lead]:
        path = cls._path(lead_id)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return Lead(**data)

    @classmethod
    def add_files(cls, lead_id: str, new_keys: list[str]) -> Lead:
        lead = cls.get(lead_id)
        if not lead:
            raise FileNotFoundError(f"Lead {lead_id} not found")
        # voorkom dubbelen
        existing = set(lead.uploaded_files or [])
        for k in new_keys:
            if k not in existing:
                lead.uploaded_files.append(k)
        return cls.upsert(lead)

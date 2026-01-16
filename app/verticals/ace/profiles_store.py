from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_PROFILES = 10


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def profiles_path() -> Path:
    # naast je other ace data
    return Path(__file__).resolve().parent / "data" / "profiles.json"


@dataclass(frozen=True)
class DiscountProfile:
    profileCode: str
    standaardKortingPct: float
    maxExtraKortingPct: float
    beschrijving: str | None = None
    active: bool = True
    updatedAt: str | None = None


def _validate_pct(name: str, v: float) -> None:
    if v < 0:
        raise ValueError(f"{name} must be >= 0")
    if v > 100:
        raise ValueError(f"{name} must be <= 100")


def load_profiles() -> list[DiscountProfile]:
    p = profiles_path()
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    items = data.get("profiles", [])
    out: list[DiscountProfile] = []
    for it in items:
        out.append(DiscountProfile(**it))
    return out


def save_profiles(profiles: list[DiscountProfile]) -> None:
    p = profiles_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "version": 1,
        "profiles": [dict(**vars(x)) for x in profiles],
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_profile(
    *,
    profileCode: str,
    standaardKortingPct: float,
    maxExtraKortingPct: float,
    beschrijving: str | None,
    active: bool = True,
) -> tuple[list[DiscountProfile], DiscountProfile | None, DiscountProfile]:
    profileCode = (profileCode or "").strip()
    if not profileCode:
        raise ValueError("profileCode is required")
    _validate_pct("standaardKortingPct", float(standaardKortingPct))
    _validate_pct("maxExtraKortingPct", float(maxExtraKortingPct))

    profiles = load_profiles()
    existing = next((p for p in profiles if p.profileCode == profileCode), None)

    if existing is None and len(profiles) >= MAX_PROFILES:
        raise ValueError(f"Max profiles reached ({MAX_PROFILES})")

    updated = DiscountProfile(
        profileCode=profileCode,
        standaardKortingPct=float(standaardKortingPct),
        maxExtraKortingPct=float(maxExtraKortingPct),
        beschrijving=(beschrijving or "").strip() or None,
        active=bool(active),
        updatedAt=_utc_now_iso(),
    )

    new_list: list[DiscountProfile] = [
        p for p in profiles if p.profileCode != profileCode
    ]
    new_list.append(updated)
    new_list.sort(key=lambda x: x.profileCode)

    save_profiles(new_list)
    return new_list, existing, updated


def delete_profile(
    profileCode: str,
) -> tuple[list[DiscountProfile], DiscountProfile | None]:
    profileCode = (profileCode or "").strip()
    profiles = load_profiles()
    existing = next((p for p in profiles if p.profileCode == profileCode), None)
    new_list = [p for p in profiles if p.profileCode != profileCode]
    save_profiles(new_list)
    return new_list, existing


def known_profile_codes() -> set[str]:
    return {p.profileCode for p in load_profiles() if p.active}

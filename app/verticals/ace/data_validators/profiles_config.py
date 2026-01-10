from __future__ import annotations

# MVP: static config (later UI/manageable)
ALLOWED_PROFILES = {"STANDARD", "SILVER", "GOLD", "PLATINUM"}

# Optional: als je profielen zones reference'en (nu alvast klaarzetten)
# Bijvoorbeeld: sommige profielen mogen alleen in bepaalde transport-zones bestaan.
PROFILE_ALLOWED_ZONES: dict[str, set[str]] = {
    # "STANDARD": {"A", "B"},
    # "GOLD": {"A"},
}

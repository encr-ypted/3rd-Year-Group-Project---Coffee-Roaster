"""Roast profile target bean temperatures (°C)."""

ROAST_PROFILES = {
    "light": 196.0,
    "medium": 210.0,
    "medium-dark": 220.0,
    "dark": 230.0,
    "default": 200.0,
}


def target_for_profile(profile_id: str) -> float:
    return ROAST_PROFILES.get(profile_id, ROAST_PROFILES["default"])

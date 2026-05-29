"""
Central configuration for the coffee roaster hardware and logging.

API settings stay in api/main.py — not configured here.
"""

import os

# Telemetry & control timing
TELEMETRY_INTERVAL_S = 0.5
ROR_WINDOW_SAMPLES = 12
HEATER_CONTROL_WINDOW_S = 1.0

# Safety & state machine (°C)
MAX_SAFE_TEMP_C = 250.0
OVERSHOOT_CUTOFF_C = 15.0
PREHEAT_THRESHOLD_C = 150.0

COOL_DOWN_TEMP_C = 34.0

# GPIO (BCM pins for gpiozero)
HEATER_GPIO = 18
FAN_PWM_GPIO = 12
FAN_PWM_FREQUENCY_HZ = 1000

THERMOCOUPLE_CS_GPIO = 8
THERMOCOUPLE_SCLK_GPIO = 11
THERMOCOUPLE_DO_GPIO = 9

# Fan (low-side PWM — active_high=False in RoasterMotor)
FAN_DEFAULT_SPEED = 1.0

# Thermocouple (MAX31855) — raw reading only (no software smoothing)
THERMOCOUPLE_STARTUP_DELAY_S = 0.5

# PID
PID_KP = 1.8
PID_KI = 0.09
PID_KD = 0
PID_OUT_MIN = 0.0
PID_OUT_MAX = 100.0
PID_INTEGRAL_LIMIT = 500.0

# Roast profiles — single source of truth for UI + PID target (°C)
ROAST_PROFILES = {
    "light": {
        "target_c": 196.0,
        "name": "Light",
        "desc": "Fruity & bright",
    },
    "medium": {
        "target_c": 210.0,
        "name": "Medium",
        "desc": "Balanced & smooth",
    },
    "medium-dark": {
        "target_c": 220.0,
        "name": "Med-Dark",
        "desc": "Rich & full-bodied",
    },
    "dark": {
        "target_c": 230.0,
        "name": "Dark",
        "desc": "Bold & smoky",
    },
    "default": {
        "target_c": 210.0,
        "name": "Default",
        "desc": "",
    },
}

# Order shown on the dashboard (default is fallback only, not listed)
ROAST_PROFILE_ORDER = ["light", "medium", "medium-dark", "dark"]


def target_for_profile(profile_id):
    entry = ROAST_PROFILES.get(profile_id) or ROAST_PROFILES["default"]
    return float(entry["target_c"])


def list_roast_profiles():
    profiles = []
    for profile_id in ROAST_PROFILE_ORDER:
        if profile_id not in ROAST_PROFILES:
            continue
        entry = ROAST_PROFILES[profile_id]
        profiles.append(
            {
                "id": profile_id,
                "name": entry["name"],
                "target_c": entry["target_c"],
                "desc": entry.get("desc", ""),
            }
        )
    return profiles


# Data logging (always under backend/ unless ROASTER_LOG_FOLDER is absolute)
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_log_dir = os.getenv("ROASTER_LOG_FOLDER", "logs")
LOG_FOLDER = _log_dir if os.path.isabs(_log_dir) else os.path.join(_BACKEND_DIR, _log_dir)
LOG_INDEX_FILE = "roasts_index.csv"
HARDWARE_MODE = os.getenv("ROASTER_HARDWARE_MODE", "pi")

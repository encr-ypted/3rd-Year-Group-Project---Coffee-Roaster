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

#Fan stays on until it cools till this temperature after a roast
COOL_DOWN_TEMP_C = 33

# GPIO (BCM pins for gpiozero)
# Heater SSR — GPIO 23 (physical pin 16). LCD backlight is GPIO 22, not 23.
HEATER_GPIO = 23
FAN_PWM_GPIO = 12
FAN_PWM_FREQUENCY_HZ = 1000

# MAX31855 on SPI0 — SCLK 11, MOSI 10, MISO 9 (enable: dtparam=spi=on)
# Single probe only — do not use THERMOCOUPLE_BEAN_* / THERMOCOUPLE_AIR_* (removed).
THERMOCOUPLE_CS_GPIO = 7
THERMOCOUPLE_SCLK_GPIO = 11
THERMOCOUPLE_DO_GPIO = 9

# Fan (low-side PWM duty 0.0–1.0; active_high=False in RoasterMotor)
FAN_DEFAULT_SPEED = 1.0

# Soft-start: ramp PWM in steps when the fan turns on (set FAN_RAMP_STEPS = 0 to disable)
FAN_RAMP_STEPS = 15
FAN_RAMP_STEP_DELAY_S = 0.12

# Thermocouple (MAX31855) — raw reading only (no software smoothing)
THERMOCOUPLE_STARTUP_DELAY_S = 0.5

# Main roast API (api/main.py): "mpc" or "pid"
HEATER_CONTROLLER = "mpc"

# Hardware bench initial mode (switchable from the bench UI without restart)
BENCH_DEFAULT_CONTROLLER = "mpc"

# PID (legacy — set HEATER_CONTROLLER = "pid" to use)
PID_KP = 1.8
PID_KI = 0.09
PID_KD = 0
PID_OUT_MIN = 0.0
PID_OUT_MAX = 100.0
PID_INTEGRAL_LIMIT = 500.0

# MPC — first-order roast model + duty search (sami_backend/coffeeControlCodeMPC.py)
MPC_AMBIENT_C = 25.0
MPC_MODEL_A = 0.9978
MPC_MODEL_B = 0.0058
MPC_PREDICTION_HORIZON = 120
MPC_DUTY_STEP = 1
MPC_WEIGHT_TRACKING = 5.0
MPC_WEIGHT_HEATER_CHG = 0.1
MPC_WEIGHT_OVERSHOOT = 2.0
MPC_OVERSHOOT_BAND_C = 10.0
MPC_UNSAFE_PENALTY = 100000.0
MPC_OUT_MIN = 0.0
MPC_OUT_MAX = 100.0

# Sigmoid setpoint ramp defaults (see hardware/roast_ramp.py)
#   setpoint = span / (1 + exp(-steepness * (t_min - midpoint_min))) + start
DEFAULT_RAMP_MIDPOINT_MIN = 2.0
DEFAULT_RAMP_STEEPNESS = 1.0

# Roast profiles — final target (°C) + sigmoid ramp shape
ROAST_PROFILES = {
    "light": {
        "target_c": 196.0,
        "ramp_midpoint_min": 2.5,
        "ramp_steepness": 0.9,
        "name": "Light",
        "desc": "Fruity & bright",
    },
    "medium": {
        "target_c": 210.0,
        "ramp_midpoint_min": 2.0,
        "ramp_steepness": 1.0,
        "name": "Medium",
        "desc": "Balanced & smooth",
    },
    "medium-dark": {
        "target_c": 220.0,
        "ramp_midpoint_min": 1.8,
        "ramp_steepness": 1.1,
        "name": "Med-Dark",
        "desc": "Rich & full-bodied",
    },
    "dark": {
        "target_c": 230.0,
        "ramp_midpoint_min": 1.6,
        "ramp_steepness": 1.2,
        "name": "Dark",
        "desc": "Bold & smoky",
    },
    "default": {
        "target_c": 210.0,
        "ramp_midpoint_min": DEFAULT_RAMP_MIDPOINT_MIN,
        "ramp_steepness": DEFAULT_RAMP_STEEPNESS,
        "name": "Default",
        "desc": "",
    },
}

# Order shown on the dashboard (default is fallback only, not listed)
ROAST_PROFILE_ORDER = ["light", "medium", "medium-dark", "dark"]


def profile_entry(profile_id):
    return ROAST_PROFILES.get(profile_id) or ROAST_PROFILES["default"]


def target_for_profile(profile_id):
    return float(profile_entry(profile_id)["target_c"])


def ramp_sigmoid_for_profile(profile_id):
    entry = profile_entry(profile_id)
    return {
        "midpoint_min": float(
            entry.get("ramp_midpoint_min", DEFAULT_RAMP_MIDPOINT_MIN)
        ),
        "steepness": float(entry.get("ramp_steepness", DEFAULT_RAMP_STEEPNESS)),
    }


def list_roast_profiles():
    profiles = []
    for profile_id in ROAST_PROFILE_ORDER:
        if profile_id not in ROAST_PROFILES:
            continue
        entry = ROAST_PROFILES[profile_id]
        ramp = ramp_sigmoid_for_profile(profile_id)
        profiles.append(
            {
                "id": profile_id,
                "name": entry["name"],
                "target_c": entry["target_c"],
                "ramp_midpoint_min": ramp["midpoint_min"],
                "ramp_steepness": ramp["steepness"],
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

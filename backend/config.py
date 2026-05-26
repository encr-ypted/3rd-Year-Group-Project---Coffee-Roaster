"""
Central configuration for the coffee roaster hardware and logging.

API settings stay in api/main.py — not configured here.
"""

import os

# Telemetry & control timing
TELEMETRY_INTERVAL_S = 0.5
ROR_WINDOW_SAMPLES = 12
HEATER_CONTROL_WINDOW_S = 2.0

# Safety & state machine (°C)
MAX_SAFE_TEMP_C = 250.0
OVERSHOOT_CUTOFF_C = 15.0
PREHEAT_THRESHOLD_C = 150.0
COOL_DOWN_TEMP_C = 50.0

# GPIO (BCM pins for gpiozero)
HEATER_GPIO = 18
FAN_PWM_GPIO = 12
FAN_PWM_FREQUENCY_HZ = 1000

THERMOCOUPLE_CS_GPIO = 8
THERMOCOUPLE_SCLK_GPIO = 11
THERMOCOUPLE_DO_GPIO = 9

# Fan (low-side PWM — active_high=False in RoasterMotor)
FAN_DEFAULT_SPEED = 1.0

# Thermocouple (MAX31855)
THERMOCOUPLE_EMA_ALPHA = 0.2
THERMOCOUPLE_STARTUP_DELAY_S = 0.5

# PID
PID_KP = 4.0
PID_KI = 0.05
PID_KD = 1.5
PID_OUT_MIN = 0.0
PID_OUT_MAX = 100.0
PID_INTEGRAL_LIMIT = 500.0

# Roast profiles (target bean temp °C)
ROAST_PROFILES = {
    "light": 196.0,
    "medium": 210.0,
    "medium-dark": 220.0,
    "dark": 230.0,
    "default": 200.0,
}


def target_for_profile(profile_id: str) -> float:
    return ROAST_PROFILES.get(profile_id, ROAST_PROFILES["default"])


# Data logging
LOG_FOLDER = os.getenv("ROASTER_LOG_FOLDER", "logs")
LOG_INDEX_FILE = "roasts_index.csv"
HARDWARE_MODE = os.getenv("ROASTER_HARDWARE_MODE", "pi")

# Smart Coffee Roaster — Backend

Python backend: **WebSocket API**, **GPIO hardware control**, **roast logging**, and **ML-ready CSV data**.

## Overview

```
Nuxt dashboard  →  ws://<pi>:8000/ws/telemetry
                      ↓
              api/main.py (FastAPI)
                      ↓
         hardware/controller.py (RoasterController)
                      ↓
    thermocouple · heater · motor · MPC/PID · roast_logger
```

## Two APIs (do not run both on the Pi at once)

| | Roast | Hardware bench |
|--|-------|----------------|
| **Run** | `python api/main.py` | `python api/hardware_test.py` |
| **Port** | 8000 | 8001 |
| **WebSocket** | `/ws/telemetry` | `/ws/bench` |
| **Code** | `hardware/controller.py` | `hardware/hardware_test_bench.py` |

Bench UI: frontend `/hardware-test` — fan, heater, PID/MPC tuning, E-stop.

## Quick start (Raspberry Pi)

Venv lives at **`CoffeeController/.venv`** (project root, sibling of `backend/`).

```bash
cd ~/Desktop/CoffeeController
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd backend
../.venv/bin/python3 api/main.py   # roast API + LCD on the Pi (default)
```

Dashboard: `ws://127.0.0.1:8000/ws/telemetry`

LCD is **on by default** when `HARDWARE_MODE=pi` in `config.py`. Disable with `ROASTER_LCD=0` or force on with `--lcd`.

### Boot on startup (Raspberry Pi)

Full guide (install, update, uninstall): **`deploy/README.md`**.

```bash
cd backend
chmod +x deploy/install-service.sh
sudo ./deploy/install-service.sh
```

Remove boot deployment: `sudo ./deploy/uninstall-service.sh` (see `deploy/README.md`).

Standalone LCD only: `python hardware/display/lcd.py`.

**Local UI without GPIO:** `python api/mock_ui_server.py` (stdlib only, port 8000).

## WebSocket — roast API

### Commands (client → server)

| Action | JSON |
|--------|------|
| Start roast | `{"action":"START_ROAST","profile_id":"medium"}` |
| Stop & cool | `{"action":"STOP_ROAST"}` |
| Resume | `{"action":"RESUME_ROAST"}` |
| Finish now | `{"action":"FINISH_ROAST"}` |
| Emergency | `{"action":"E_STOP"}` |
| State sync | `{"action":"GET_STATE"}` |

### Telemetry (server → client, ~2 Hz)

```json
{
  "type": "telemetry",
  "timestamp": 42.5,
  "temp": 187.3,
  "target": 210.0,
  "setpoint": 185.2,
  "ramp_midpoint_min": 2.0,
  "ramp_steepness": 1.0,
  "heater_pwm": 65,
  "fan_pwm": 100,
  "state": "ROASTING",
  "heater_halted": false,
  "sensor_fault": null,
  "can_resume": false,
  "test_spin": false
}
```

RoR is still written to roast CSV logs for ML; it is not sent on the WebSocket (dashboard does not display it).

## State machine

| State | Meaning |
|-------|---------|
| `IDLE` | Off |
| `PREHEAT` | Warming toward profile target |
| `ROASTING` | At/above preheat threshold (150 °C) |
| `COOLING` | User stopped; fan on until cool |
| `ERROR` | Over-temp (>250 °C) |

- `START_ROAST` → `PREHEAT`
- Temp ≥ **150 °C** → `ROASTING`
- `STOP_ROAST` → `COOLING`
- Temp ≤ **33 °C** in `COOLING` → `IDLE`
- Temp > **250 °C** → `ERROR`

## Control

- **Heater:** time-proportional relay (`HEATER_CONTROL_WINDOW_S = 1.0` s). Duty from `MPCController` or `PIDController` — set `HEATER_CONTROLLER` in `config.py`.
- **Setpoint ramp:** sigmoid from bean start temp to profile target (`hardware/control/roast_ramp.py`).
- **Overshoot:** heater forced to 0% when temp > target + **15 °C**.
- **Fan:** on during preheat/roast/cool; off at idle after cool-down.

## Hardware modules

| File | Role |
|------|------|
| `devices/thermocouple.py` | MAX31855, single probe, raw reading |
| `devices/heater.py` | SSR relay, time-proportional `apply_output()` |
| `devices/motor.py` | Fan PWM (GPIO 12) |
| `control/heater_control.py` | Factory: MPC or PID |
| `control/mpc.py` / `control/pid.py` | Heater duty 0–100% |
| `control/roast_ramp.py` | Sigmoid setpoint curve |
| `roast_logger.py` | CSV + JSON metadata |
| `hardware_test_bench.py` | Bench-only GPIO test harness |
| `display/st7796.py` / `display/lcd.py` | SPI driver + live WebSocket dashboard |

## Configuration (`config.py`)

| Setting | Value |
|---------|-------|
| `HEATER_GPIO` | 23 |
| `THERMOCOUPLE_CS_GPIO` | 7 (SPI0 CE1) |
| `FAN_PWM_GPIO` | 12 |
| `COOL_DOWN_TEMP_C` | 33 |
| `HEATER_CONTROLLER` | `"mpc"` or `"pid"` |
| `BENCH_DEFAULT_CONTROLLER` | bench startup mode |

Profiles: `GET /api/profiles` — same data as `ROAST_PROFILES` in config.

## Data logging

- `logs/roast_<id>.csv` — time series
- `logs/roast_<id>_meta.json` — session metadata
- `logs/roasts_index.csv` — index

CSV includes `ror_c_per_min` for ML. Examples: `examples/roast_data_formats.json`.

HTTP: `GET /api/roasts`, `GET /api/roasts/{roast_id}`.

## Project layout

```
backend/
├── config.py
├── api/
│   ├── main.py              # Roast API (8000)
│   ├── hardware_test.py     # Bench API (8001)
│   └── mock_ui_server.py    # Dev mock (no GPIO)
├── hardware/
│   ├── controller.py           # Roast orchestration
│   ├── hardware_test_bench.py  # Bench GPIO harness
│   ├── roast_logger.py
│   ├── devices/                # thermocouple, heater, motor
│   ├── control/                # pid, mpc, heater_control, roast_ramp
│   └── display/                # st7796.py (driver), lcd.py (dashboard)
├── deploy/                     # systemd install + uninstall scripts
├── docs/lcd_st7796_test.md
├── examples/roast_data_formats.json
└── requirements.txt
```

## GPIO pinout

Full wiring table (physical pins + BCM GPIO): **`docs/gpio_pinout.md`**.

## LCD

See `docs/lcd_st7796_test.md`. LCD code lives in `hardware/display/`. LCD uses **SPI1** (CS GPIO 17); thermocouple stays on **SPI0**.

## Troubleshooting

### `/dev/spidev0.0` missing

```bash
sudo raspi-config   # Interface Options → SPI → Enable
sudo reboot
ls /dev/spidev*
```

Thermocouple CS: GPIO **7** (`THERMOCOUPLE_CS_GPIO`). Add user to `spi,gpio` if permission errors.

### WebSocket 403 on `/ws/telemetry`

Wrong server on port 8000 — run `main.py`, not `hardware_test.py`.

### Thermocouple fault

Fix probe wiring before enabling the heater.

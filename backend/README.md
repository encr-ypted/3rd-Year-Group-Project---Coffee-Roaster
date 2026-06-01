# Smart Coffee Roaster — Backend

Python backend for the Smart Coffee Roaster: **WebSocket API**, **hardware control**, **roast logging**, and **ML-ready data**.

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Nuxt dashboard (WebSocket client)                            │
└───────────────────────────┬─────────────────────────────────┘
                            │ ws://127.0.0.1:8000/ws/telemetry
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI (`api/main.py`)                                    │
│  • WebSocket commands → RoasterController                   │
│  • Broadcast telemetry to all clients                       │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  RoasterController (`hardware/controller.py`)               │
│  • State machine (PREHEAT → ROASTING → COOLING → IDLE)      │
│  • Two async loops: telemetry + heater                      │
└───────────────────────────┬─────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Hardware modules                                           │
│  • thermocouple.py — temperature (MAX31855 raw)             │
│  • heater.py — relay, time-proportional power               │
│  • motor.py — fan (low-side PWM, GPIO 12)                   │
│  • pid.py — PID loop                                        │
│  • roast_logger.py — CSV + JSON metadata                    │
└─────────────────────────────────────────────────────────────┘
```

## Hardware bench test (separate API)

For first power-on / wiring checks, use the **bench server** — not the roast API.

| | Roast dashboard | Hardware bench |
|--|-----------------|----------------|
| **Run** | `python api/main.py` | `python api/hardware_test.py` |
| **Port** | 8000 | 8001 |
| **WebSocket** | `/ws/telemetry` | `/ws/bench` |
| **Code** | `hardware/controller.py` | `verified_hardware/full_control.py` |

Do **not** run both servers on the Pi at once (GPIO conflict).

1. `python api/hardware_test.py`
2. Open frontend `/hardware-test`
3. WebSocket `/ws/bench` — `FAN_SET`, `HEAT_START`, `PID_SET`, `E_STOP` (see `api/hardware_test.py`).

## Quick start

```bash
cd backend
pip install -r requirements.txt
python api/main.py
```

Dashboard WebSocket: `ws://127.0.0.1:8000/ws/telemetry`

> **Note:** `main.py` instantiates `RoasterController` (real GPIO). Run on a **Raspberry Pi** with thermocouple, heater relay, and fan wired.

## WebSocket workflow

### Client → server (commands)

| Action | JSON | Effect |
|--------|------|--------|
| Start roast | `{"action":"START_ROAST","profile_id":"medium"}` | `PREHEAT`, logging, fan on |
| Stop & cool | `{"action":"STOP_ROAST"}` | `COOLING`, heater off, fan on, log still open |
| Resume | `{"action":"RESUME_ROAST"}` | Back to preheat/roast, same log file |
| Finish now | `{"action":"FINISH_ROAST"}` | Save log immediately, keep cooling to 34°C |
| Emergency | `{"action":"E_STOP"}` | `IDLE`, heater off, fan 100% |
| State sync | `{"action":"GET_STATE"}` | Reply with current `state` |

### Server → client (telemetry)

Every ~0.5 s while roasting:

```json
{
  "type": "telemetry",
  "timestamp": 42.5,
  "temp": 187.3,
  "target": 210.0,
  "ror": 8.2,
  "heater_pwm": 65,
  "fan_pwm": 100,
  "state": "ROASTING"
}
```

On fault:

```json
{ "type": "error", "msg": "Thermocouple fault: … — roast continues; check probe wiring" }
```

## RoasterController — state machine

| State | Meaning |
|-------|---------|
| `IDLE` | Off |
| `PREHEAT` | Warming toward profile target |
| `ROASTING` | At/above preheat threshold (150 °C) |
| `COOLING` | User stopped; fan on until cool |
| `ERROR` | Over-temp (>250 °C) |

**Transitions**

- `START_ROAST` → `PREHEAT`
- Temp ≥ **150 °C** → `ROASTING`
- `STOP_ROAST` → `COOLING`
- Temp ≤ **34 °C** in `COOLING` → `IDLE` (fan off)
- Temp > **250 °C** → `ERROR`

**Profile targets (°C)**

| Profile | Target |
|--------|--------|
| light | 196 |
| medium | 210 |
| medium-dark | 220 |
| dark | 230 |
| default | 200 |

## Control loops

### 1. Telemetry loop (~2 Hz)

- Read thermocouple (raw)
- Update `current_temp`, RoR, state
- Push WebSocket JSON
- Log samples to CSV (when session active)

### 2. Heater loop (time-proportional)

- While `PREHEAT` or `ROASTING`:
  - `output = PIDController.calculate(target_temp, current_temp)`
  - If temp > target + **15 °C** → `output = 0`
  - `await RoasterHeater.apply_output(output)` — relay on/off for **2 s** window
- Else: `heater.stop()`

**Why time-proportional?** Heater is a relay (on/off only). `40%` ≈ relay on 40% of each 2 s window.

### Fan

- `START_ROAST` / `STOP_ROAST` → `RoasterMotor.set_speed(1.0)`
- Cool-down finished or `E_STOP` → `RoasterMotor.stop()`

## Hardware modules

| File | Class | Role |
|------|-------|------|
| `thermocouple.py` | `RoasterThermocouple` | MAX31855, EMA smoothing |
| `heater.py` | `RoasterHeater` | SSR relay, `apply_output(percent)` |
| `motor.py` | `RoasterMotor` | Low-side PWM fan (MOSFET/BJT on GPIO 12) |
| `pid.py` | `PIDController` | P/I/D → 0–100% |
| `roast_logger.py` | `RoastDataLogger` | CSV + `_meta.json` |

## Data logging (ML)

On each roast:

- `logs/roast_<id>.csv` — time series (~2 Hz)
- `logs/roast_<id>_meta.json` — session metadata
- `logs/roasts_index.csv` — one row per roast

**CSV columns:** `roast_id`, `unix_ts`, `elapsed_s`, `profile_id`, `temp_c`, `temp_raw_c`, `target_c`, `temp_error_c`, `heater_pwm`, `fan_pwm`, `ror_c_per_min`, `state`, `event`

**HTTP:** `GET /api/roasts` — list sessions from `roasts_index.csv`; `GET /api/roasts/{roast_id}` — session metadata JSON.

Logs are written to `backend/logs/` (or `ROASTER_LOG_FOLDER` if set).

**JSON examples:** `examples/roast_data_formats.json`

## Configuration

Hardware and logging settings: **`config.py`** (GPIO, PID, safety limits, roast profiles). The dashboard loads profiles from **`GET /api/profiles`** (same data as `ROAST_PROFILES`).

LCD smoke test and realtime dashboard: **`docs/lcd_st7796_test.md`**,
**`hardware/lcd_st7796_test.py`**, and **`hardware/lcd_dashboard.py`**.

API host/port: **`api/main.py`** (unchanged).

Optional env vars: `ROASTER_LOG_FOLDER`, `ROASTER_HARDWARE_MODE`.

## Project layout

```
backend/
├── config.py                # Hardware / logging configuration
├── api/main.py              # Roast API (port 8000)
├── api/hardware_test.py     # Bench API (port 8001)
├── hardware/
│   ├── controller.py        # RoasterController (roast orchestration)
│   ├── thermocouple.py
│   ├── heater.py
│   ├── motor.py
│   ├── pid.py
│   └── roast_logger.py
├── verified_hardware/
│   ├── full_control.py      # HardwareTestBench (bench only)
│   ├── thermocouple.py
│   ├── heater.py
│   ├── motor.py
│   └── pid.py
├── examples/roast_data_formats.json
├── requirements.txt
└── README.md
```

## Safety notes

- **Over-temp:** >250 °C → `ERROR`, heater off
- **Overshoot:** >target + 15 °C → heater 0% for that window
- **E-STOP:** immediate relay off (`heater.stop()`)

## Troubleshooting

### `OSError: /dev/spidev0.0 does not exist`

The MAX31855 uses **SPI**. The kernel device is missing until SPI is turned on:

```bash
sudo raspi-config   # Interface Options → SPI → Enable
sudo reboot
ls /dev/spidev*     # should list spidev0.0 and spidev0.1
```

If SPI is enabled but permission errors appear:

```bash
sudo usermod -aG spi,gpio $USER
# log out and back in (or reboot)
```

Wiring (BCM): CS → GPIO **8** (see `THERMOCOUPLE_CS_GPIO` in `config.py`). SCLK/MOSI/MISO use the Pi’s hardware SPI pins (11, 10, 9 on older docs — your `config.py` notes DO on 9).

### `RuntimeError: short circuit to ground` (thermocouple)

Hardware fault from the MAX31855: probe wires shorted to ground, loose terminals, or damaged cable. Fix wiring before enabling the heater.

## Known limitations

- Heater loop blocks ~2 s per `apply_output` — PID updates once per window, not every 0.5 s.
- No mock/simulation path in current `main.py` — intended for **Raspberry Pi** hardware.
- For local UI testing without GPIO, consider re-adding a `MockHardwareManager` or running on Pi only.

## Related docs

- WebSocket JSON examples: `examples/roast_data_formats.json`
- Git-ignored runtime data: `logs/` (CSV + JSON per roast)

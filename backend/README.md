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
│  • thermocouple.py — temperature (EMA filtered)             │
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
| **Code** | `hardware/controller.py` | `hardware/test_bench.py` |

Do **not** run both servers on the Pi at once (GPIO conflict).

1. `python api/hardware_test.py`
2. Open frontend `/hardware-test`
3. **Start session** → test fan → read thermocouple → short heater pulses

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
| Stop & cool | `{"action":"STOP_ROAST"}` | `COOLING`, heater off, fan on |
| Emergency | `{"action":"E_STOP"}` | `IDLE`, heater/fan off |
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
{ "type": "error", "msg": "Thermocouple fault — emergency shutdown" }
```

## RoasterController — state machine

| State | Meaning |
|-------|---------|
| `IDLE` | Off |
| `PREHEAT` | Warming toward profile target |
| `ROASTING` | At/above preheat threshold (150 °C) |
| `COOLING` | User stopped; fan on until cool |
| `ERROR` | Sensor fault or over-temp (>250 °C) |

**Transitions**

- `START_ROAST` → `PREHEAT`
- Temp ≥ **150 °C** → `ROASTING`
- `STOP_ROAST` → `COOLING`
- Temp ≤ **50 °C** in `COOLING` → `IDLE` (fan off)
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

- Read thermocouple (raw + filtered)
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

**CSV columns:** `roast_id`, `unix_ts`, `elapsed_s`, `profile_id`, `temp_c`, `temp_raw_c`, `target_c`, `temp_error_c`, `heater_pct`, `fan_pct`, `ror_c_per_min`, `state`, `event`

**JSON examples:** `examples/roast_data_formats.json`

## Configuration

Hardware and logging settings: **`config.py`** (GPIO, PID, safety limits, roast profiles).

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
│   ├── test_bench.py        # HardwareTestBench (bench only)
│   ├── thermocouple.py
│   ├── heater.py
│   ├── motor.py
│   ├── pid.py
│   ├── profiles.py
│   └── roast_logger.py
├── examples/roast_data_formats.json
├── requirements.txt
└── README.md
```

## Safety notes

- **Over-temp:** >250 °C → `ERROR`, heater off
- **Overshoot:** >target + 15 °C → heater 0% for that window
- **E-STOP:** immediate relay off (`heater.stop()`)

## Known limitations

- Heater loop blocks ~2 s per `apply_output` — PID updates once per window, not every 0.5 s.
- No mock/simulation path in current `main.py` — intended for **Raspberry Pi** hardware.
- For local UI testing without GPIO, consider re-adding a `MockHardwareManager` or running on Pi only.

## Related docs

- WebSocket JSON examples: `examples/roast_data_formats.json`
- Git-ignored runtime data: `logs/` (CSV + JSON per roast)

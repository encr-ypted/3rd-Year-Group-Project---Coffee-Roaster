# Smart Coffee Roaster Backend

This folder contains the Raspberry Pi backend for the Smart Coffee Roaster. It controls the roast process, communicates with the frontend, monitors bean brightness with the camera, and can drive the optional LCD display.

## Files

### `MPC_Control.py`

The main roast-control script.

It:
- Reads temperature from the MAX31855 thermocouple.
- Controls the heater and fan.
- Handles preheating, bean-drop detection, and the normal roast phase.
- Uses a model predictive control (MPC) loop to follow the selected roast profile's setpoint curve.
- Writes roast telemetry to CSV files in `logs/`.
- Reads grayscale data from `grayscale_state.json`.
- Sends a roast-done notification flag when grayscale stays below the selected profile threshold for five seconds.

The grayscale notification does not automatically stop the roast, turn off the heater, or start cooling.

### `grayscale.py`

A separate camera worker for the Raspberry Pi AI camera.

It:
- Starts the camera and AI detector.
- Captures bean images.
- Calculates the average bean brightness (`mean_grayscale`).
- Writes the latest value to `grayscale_state.json`.

It runs separately from `MPC_Control.py` so camera errors, timeouts, or crashes do not interrupt the main heating, fan, thermocouple, or MPC control logic.

A grayscale value ranges from approximately 0 to 255:
- Lower values mean darker beans.
- Higher values mean lighter beans.

### `webserver.py`

The FastAPI/WebSocket backend used by the frontend.

It:
- Provides roast profiles at `/api/profiles`.
- Sends live telemetry through `/ws/telemetry`.
- Reads the newest CSV file in `logs/`.
- Sends temperature, setpoint, heater output, fan output, grayscale, roast state, and roast-done notification status to the frontend.
- Writes commands to `roaster_command.json`.

### `st7796.py`

Driver for the ST7796 SPI LCD display.

It uses SPI1 so it does not conflict with the MAX31855 thermocouple on SPI0.

### `requirements.txt`

Python dependencies for the backend.

## Roast Flow

1. The empty roasting chamber is preheated.
2. Once the preheat temperature is stable, beans are added.
3. The added beans create a temperature drop.
4. The controller detects the drop, turns the heater off, and waits for the lowest temperature.
5. Once the temperature begins rising again, the actual roast starts.
6. The controller resets roast time and follows the MPC setpoint curve toward the chosen profile target.

## Grayscale Roast-Done Notification

The camera worker measures the average brightness of the beans and writes it to `grayscale_state.json`.

During the actual roast, `MPC_Control.py` compares that value against the selected profile threshold:

| Roast profile | Notification threshold |
|---|---:|
| Light | Below 120 |
| Medium | Below 115 |
| Medium-Dark | Below 110 |
| Dark | Below 105 |

If the grayscale value remains below the selected threshold for five seconds, the backend sets `roast_done` to `true`. The frontend can then display a notification that the roast looks done.

This is notification-only. The user still decides when to stop and cool the roast.

## Running the Backend

Open three terminals on the Raspberry Pi.

### 1. Start the grayscale worker

```bash
source venv/bin/activate
python grayscale.py
```

This writes live camera data to:

```text
grayscale_state.json
```

### 2. Start the roast controller

```bash
source venv/bin/activate
python MPC_Control.py
```

This controls the thermocouple, heater, fan, preheat sequence, bean-drop detection, MPC setpoint curve, and roast logging.

### 3. Start the web server

```bash
source venv/bin/activate
python webserver.py
```

The server runs on port `8000`.

## Generated Files

### `roaster_command.json`

Written by `webserver.py` and read by `MPC_Control.py`.

Example:

```json
{
  "command": "PREHEAT",
  "target_c": 210.0,
  "profile_id": "medium"
}
```

### `grayscale_state.json`

Written by `grayscale.py` and read by `MPC_Control.py`.

Example:

```json
{
  "timestamp": 1712345678.2,
  "mean_grayscale": 94.7,
  "ok": true,
  "error": null
}
```

### `logs/roast_*.csv`

Created by `MPC_Control.py`.

Each CSV row includes time, temperature, target, setpoint, heater output, fan speed, grayscale value, grayscale threshold, roast-done notification status, and control state.

## Safety Notes

- The grayscale system is notification-only and must not replace operator judgement.
- The emergency-stop and over-temperature safety behavior remain in `MPC_Control.py`.
- If the camera worker stops, the main roast controller continues running. Grayscale will appear unavailable until the worker starts writing fresh values again.

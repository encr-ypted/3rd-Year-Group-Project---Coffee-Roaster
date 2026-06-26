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

## Adaptive Model Predictive Control (MPC)

The Smart Coffee Roaster uses an **Adaptive Model Predictive Controller (MPC)** to regulate bean temperature throughout the roast. Unlike a conventional PID controller, which reacts only to the current temperature error, the MPC predicts the future thermal behaviour of the roaster before selecting the optimum heater output. This approach is particularly well suited to coffee roasting because the process exhibits significant thermal inertia and transport delay, meaning changes in heater power may take several seconds to influence bean temperature.

At every one-second control interval, the controller predicts how the bean temperature will evolve over a finite prediction horizon using a first-order discrete thermal model. Multiple candidate heater outputs are evaluated, and the one producing the lowest overall cost is selected and applied for the next control interval. This optimisation process is repeated every second throughout the roast.

### Thermal Process Model

The roaster is approximated using the first-order discrete thermal model


$$
T_{k+1}=T_{amb}+A(T_k-T_{amb})+Bu_k
$$


where:

- \(T_k\) = current bean temperature
- \(T_{k+1}\) = predicted bean temperature one second later
- \(T_{amb}\) = ambient temperature
- \(u_k\) = heater duty cycle (%)
- \(A\) = heat retention coefficient
- \(B\) = heater effectiveness coefficient

The first term represents the ambient temperature surrounding the roaster.

The second term models the thermal inertia of the roasting system by describing how much of the previous temperature is naturally retained between consecutive control intervals.

The third term represents the heating contribution from the electric heater. Larger heater duty cycles produce greater increases in predicted bean temperature.

Rather than using this model only once, the MPC repeatedly evaluates it to predict the complete future temperature trajectory.

### Future Setpoint Prediction

Instead of assuming the future target temperature remains equal to the current setpoint, the controller predicts the actual future roast profile.

For every prediction step,


$$
r_{k+i}=\text{SetpointCurve}(t+i)
$$


where:

- \(r_{k+i}\) is the desired future temperature,
- \(t\) is the current roast time,
- \(i\) is the prediction step.

This allows the controller to anticipate future temperature changes before they occur. As the sigmoid roast profile continues to rise, the MPC can begin increasing heater power in advance rather than waiting until the setpoint has already changed.

### Prediction Horizon

For each control interval, the controller predicts bean temperature over a finite prediction horizon of approximately one minute.

For every candidate heater duty cycle between **0% and 100%**, the thermal model is recursively evaluated to generate the complete future temperature trajectory


$$
\{T_{k+1},T_{k+2},...,T_{k+N}\}
$$


where \(N\) is the prediction horizon.

This enables the controller to compare the long-term consequences of different heater outputs rather than considering only the next measurement.

### Candidate Heater Evaluation

At every control update, the controller evaluates every possible heater duty cycle from **0% to 100%**.

For each candidate heater output:

1. The future roast-profile setpoints are generated.
2. Future bean temperatures are predicted across the prediction horizon.
3. A total optimisation cost is calculated.
4. The controller stores the total cost.

After all candidate heater outputs have been evaluated, the heater duty cycle with the lowest predicted cost is selected and applied.

Mathematically,


$$
u^*=\arg\min_u J(u)
$$


where \(u^*\) represents the optimum heater duty cycle.

### Cost Function

Each candidate heater output is assigned a cost according to


$$
J=\sum_{k=1}^{N}w_t(r_k-T_k)^2+\sum_{k=1}^{N}w_oO_k^2+w_h(u_k-u_{k-1})^2
$$


where:

- \(w_t\) is the tracking-error weighting,
- \(w_o\) is the overshoot weighting,
- \(w_h\) is the heater-change weighting.

#### Tracking Error

The first term


$$
\sum_{k=1}^{N}w_t(r_k-T_k)^2
$$


penalises deviation between the predicted bean temperature and the desired roast profile throughout the prediction horizon. Larger tracking errors produce larger costs, encouraging the controller to follow the planned roast profile as accurately as possible.

#### Overshoot Penalty

The second term


$$
\sum_{k=1}^{N}w_oO_k^2
$$


penalises predicted overshoot above the desired roast profile.

Only temperatures exceeding the target contribute to this penalty, discouraging overheating while still allowing aggressive heating when the measured temperature remains below the desired profile.

#### Heater Smoothness

The third term


$$
w_h(u_k-u_{k-1})^2
$$


penalises large changes in heater duty cycle between consecutive control intervals.

Without this penalty, the optimiser may rapidly increase and decrease heater power, producing oscillatory behaviour. Penalising abrupt heater changes results in smoother control actions, reduced actuator switching, and improved thermal stability.

### Adaptive Thermal Model

Coffee roasting is not a constant thermal process.

During roasting:

- moisture evaporates,
- bean density decreases,
- airflow characteristics change,
- heat losses vary,
- the effectiveness of the heater changes.

Consequently, a fixed thermal model gradually becomes inaccurate.

To compensate, the controller continuously compares predicted and measured temperatures.

If a sustained prediction error is detected, the heater effectiveness coefficient (**B**) is automatically adjusted within predefined minimum and maximum limits.

If the measured temperature rises faster than predicted, the controller increases **B**, indicating that the heater is more effective than previously estimated.

If the measured temperature rises more slowly than predicted, **B** is reduced.

This adaptive mechanism continually improves model accuracy throughout the roast while preventing unrealistic parameter values.

### Bean-Drop Detection

Before roasting begins, the chamber is preheated to the selected temperature.

When green coffee beans are added, the thermocouple detects the characteristic temperature drop caused by the colder beans entering the chamber.

The controller automatically identifies this event, temporarily suspends normal roast control, waits until the temperature reaches its minimum, and detects the point at which the beans begin warming again.

At this instant:

- the roast timer is reset,
- the sigmoid roast profile begins,
- the MPC controller becomes active.

This ensures the roast profile is synchronised with the true start of bean heating rather than the preheating stage.

### Control Cycle

Every second the controller performs the following sequence:

1. Read the current bean temperature from the thermocouple.
2. Generate future sigmoid roast-profile setpoints.
3. Predict future bean temperatures for every candidate heater output.
4. Calculate the optimisation cost for every candidate.
5. Select the heater duty cycle producing the minimum cost.
6. Apply the selected heater output.
7. Update the adaptive heater-effectiveness coefficient if required.
8. Record telemetry for the dashboard and CSV log files.

This optimisation process repeats continuously throughout the roast, allowing the controller to accurately track a continuously changing roast profile while automatically compensating for changing thermal dynamics.

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

import time
import csv
import os
from datetime import datetime

import board
import digitalio
import adafruit_max31855
from gpiozero import DigitalOutputDevice, Motor, PWMOutputDevice


TARGET_C = 180.0
MAX_SAFE_TEMP_C = 250.0
LOG_FOLDER = "logs"
COMMAND_FILE = "roaster_command.txt"

HEATER_GPIO = 18
CONTROL_WINDOW_S = 1.0

IN1 = 23
IN2 = 24
ENA = 12

MOTOR_ON_SPEED = 0.0
MOTOR_OFF_SPEED = 1.0

FAN_RAMP_TIME_S = 5.0
FAN_RAMP_STEPS = 10
fan_ramp_done = False

AMBIENT_C = 25.0
MODEL_A = 0.9555
MODEL_B = 0.1173

PREDICTION_HORIZON = 30
DUTY_STEP = 1

WEIGHT_TRACKING = 1.0
WEIGHT_HEATER_CHG_IN = 0.2
WEIGHT_OVERSHOOT = 20.0

previous_heater_output = 0.0
previous_temp_for_ror = None
previous_time_for_ror = None


spi = board.SPI()
cs = digitalio.DigitalInOut(board.D8)
sensor = adafruit_max31855.MAX31855(spi, cs)

heater = DigitalOutputDevice(HEATER_GPIO, active_high=True, initial_value=False)

motor = Motor(forward=IN1, backward=IN2)
enable = PWMOutputDevice(ENA, frequency=1000)


def fan_on():
    enable.value = MOTOR_ON_SPEED
    motor.forward()


def fan_off():
    enable.value = MOTOR_OFF_SPEED
    motor.forward()


def fan_ramp_start():
    print("Ramp fan before heater si started")

    for i in range(FAN_RAMP_STEPS + 1):
        speed = MOTOR_OFF_SPEED - ((MOTOR_OFF_SPEED - MOTOR_ON_SPEED) * (i / FAN_RAMP_STEPS))
        enable.value = speed
        motor.forward()
        print(f"Fan ramp value: {speed:.2f}")
        time.sleep(FAN_RAMP_TIME_S / FAN_RAMP_STEPS)

    enable.value = MOTOR_ON_SPEED
    print("Fan ramp complete so heater now allowed.")


def read_command():
    if not os.path.exists(COMMAND_FILE):
        return "IDLE", TARGET_C

    with open(COMMAND_FILE, "r") as file:
        text = file.read().strip()

    if text.startswith("RUN,"):
        try:
            _, target = text.split(",")
            return "RUN", float(target)
        except Exception:
            return "RUN", TARGET_C

    return text, TARGET_C


def estimate_ror(current_temp, previous_temp, dt):
    if previous_temp is None or dt <= 0:
        return 0.0

    return ((current_temp - previous_temp) / dt) * 60.0


def calculate_mpc(temp_c, target_c):
    global previous_heater_output

    best_duty = 0.0
    best_cost = float("inf")

    for duty in range(0, 101, DUTY_STEP):
        predicted_temp = temp_c
        cost = 0.0

        for _ in range(PREDICTION_HORIZON):
            predicted_temp = (
                AMBIENT_C
                + MODEL_A * (predicted_temp - AMBIENT_C)
                + MODEL_B * duty
            )

            error = target_c - predicted_temp
            cost += WEIGHT_TRACKING * (error ** 2)

            if predicted_temp > target_c:
                cost += WEIGHT_OVERSHOOT * ((predicted_temp - target_c) ** 2)

            if predicted_temp > MAX_SAFE_TEMP_C:
                cost += 100000

        cost += WEIGHT_HEATER_CHG_IN * ((duty - previous_heater_output) ** 2)

        if cost < best_cost:
            best_cost = cost
            best_duty = duty

    previous_heater_output = best_duty
    return float(best_duty)


os.makedirs(LOG_FOLDER, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = f"{LOG_FOLDER}/roast_{timestamp}.csv"

with open(log_file, "w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow([
        "time_s",
        "temp_c",
        "target_c",
        "heater_output_percent",
        "fan_speed",
        "ror_c_per_min",
        "state"
    ])


print(f"Default target temperature: {TARGET_C} °C")
print(f"Logging to: {log_file}")


start_time = time.time()

try:
    fan_off()
    fan_ramp_start()
    fan_ramp_done = True

    while True:
        elapsed = round(time.time() - start_time, 1)
        command, target_c = read_command()

        if command == "E_STOP":
            heater.off()
            fan_off()
            print("EMERGENCY STOP from dashboard")
            break

        try:
            temp_c = sensor.temperature

            if temp_c is None:
                raise RuntimeError("No temperature reading")

            now = time.time()

            if previous_time_for_ror is None:
                ror = 0.0
            else:
                dt = now - previous_time_for_ror
                ror = estimate_ror(temp_c, previous_temp_for_ror, dt)

            previous_temp_for_ror = temp_c
            previous_time_for_ror = now

            if command == "IDLE":
                heater_output = 0.0
                state = "IDLE"

            elif command == "STOP":
                heater_output = 0.0
                state = "COOLING_FROM_DASHBOARD"

            else:
                heater_output = calculate_mpc(temp_c, target_c)
                heater_output = round(heater_output, 1)

                if temp_c > MAX_SAFE_TEMP_C:
                    heater_output = 0.0
                    state = "SAFETY_SHUTDOWN_OVERTEMP"

                elif temp_c >= target_c:
                    heater_output = 0.0
                    state = "ABOVE_TARGET_HEATER_OFF"

                elif temp_c >= target_c - 5 and ror > 2.0:
                    heater_output = min(heater_output, 20.0)
                    state = "APPROACHING_TARGET_LIMITED_HEAT"

                elif temp_c >= target_c - 10 and ror > 5.0:
                    heater_output = min(heater_output, 40.0)
                    state = "FAST_RISE_LIMITED_HEAT"

                else:
                    state = "RUNNING_MPC_FAN_TEST"

            if not fan_ramp_done:
                heater_output = 0.0
                state = "WAITING_FOR_FAN_RAMP"

            with open(log_file, "a", newline="") as file:
                writer = csv.writer(file)
                writer.writerow([
                    elapsed,
                    round(temp_c, 2),
                    target_c,
                    heater_output,
                    MOTOR_ON_SPEED,
                    round(ror, 2),
                    state
                ])

            print(
                f"{elapsed}s | Temp: {temp_c:.2f} °C | "
                f"Target: {target_c:.1f} °C | "
                f"RoR: {ror:.1f} °C/min | "
                f"MPC Heater: {heater_output:.1f}% | "
                f"Fan: {MOTOR_ON_SPEED:.1f} | {state}"
            )

            on_time = CONTROL_WINDOW_S * (heater_output / 100)
            off_time = CONTROL_WINDOW_S - on_time

            if heater_output > 0:
                heater.on()
                time.sleep(on_time)
                heater.off()
                time.sleep(off_time)
            else:
                heater.off()
                time.sleep(CONTROL_WINDOW_S)

        except Exception as e:
            heater_output = previous_heater_output
            ror = 0.0

            print(f"Sensor error: {e} so keeping same duty: {heater_output:.1f}%")

            state = "SENSOR_ERROR_KEEPING_DUTY"

            with open(log_file, "a", newline="") as file:
                writer = csv.writer(file)
                writer.writerow([
                    elapsed,
                    "NaN",
                    target_c,
                    heater_output,
                    MOTOR_ON_SPEED,
                    ror,
                    state
                ])

            on_time = CONTROL_WINDOW_S * (heater_output / 100)
            off_time = CONTROL_WINDOW_S - on_time

            if heater_output > 0:
                heater.on()
                time.sleep(on_time)
                heater.off()
                time.sleep(off_time)
            else:
                heater.off()
                time.sleep(CONTROL_WINDOW_S)

except KeyboardInterrupt:
    heater.off()
    fan_off()
    print("\nStopped safely. Heater OFF. Fan OFF.")
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
CONTROL_WINDOW_S = 1

IN1 = 23
IN2 = 24
ENA = 12


MOTOR_ON_SPEED = 0
MOTOR_OFF_SPEED = 1


AMBIENT_C = 25.0
MODEL_A = 0.9555
MODEL_B =  0.1173

PREDICTION_HORIZON = 30
DUTY_STEP = 1

WEIGHT_TRACKING = 2 #decrese if too agressive
WEIGHT_HEATER_CHG_IN = 0.1 #increase if heater jumps a lot
WEIGHT_OVERSHOOT = 5  #increase if it overshoots the target

previous_heater_output = 0


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


def read_command():
    if not os.path.exists(COMMAND_FILE):
        return "IDLE"

    with open(COMMAND_FILE, "r") as file:
        return file.read().strip()


def calculate_mpc(temp_c):
    global previous_heater_output

    best_duty = 0.0
    best_cost = float("inf")

    for duty in range(0, 101, DUTY_STEP):
        predicted_temp = temp_c
        cost = 0.0

        for _ in range(PREDICTION_HORIZON):
            predicted_temp = (
                AMBIENT_C + MODEL_A * (predicted_temp - AMBIENT_C) + MODEL_B * duty
            )

            error = TARGET_C - predicted_temp
            cost += WEIGHT_TRACKING * (error ** 2)

            if predicted_temp > TARGET_C + 10:
                cost += WEIGHT_OVERSHOOT * ((predicted_temp - TARGET_C) ** 2)

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
        "state"
    ])


print("Coffee roaster MPC + fan control started.")
print("Dashboard controls: IDLE / RUN / STOP / E_STOP")
print(f"Target temperature: {TARGET_C} °C")
print(f"Loggig to: {log_file}")



start_time = time.time()

try:
    fan_on()

    while True:
        elapsed = round(time.time() - start_time, 1)
        command = read_command()

        if command == "E_STOP":
            heater.off()
            fan_off()
            print("EMERGENCY STOP from dashboard")
            break

        try:
            temp_c = sensor.temperature

            if temp_c is None:
                raise RuntimeError("No temperature reading")

            if command == "IDLE":
                heater_output = 0.0
                state = "IDLE"

            elif command == "STOP":
                heater_output = 0.0
                state = "COOLING_FROM_DASHBOARD"

            else:
                heater_output = calculate_mpc(temp_c)
                heater_output = round(heater_output, 1)

                if temp_c > MAX_SAFE_TEMP_C:
                    heater_output = 0.0
                    state = "SAFETY_SHUTDOWN_OVERTEMP"

                elif temp_c > TARGET_C + 15:
                    heater_output = 0.0
                    state = "ABOVE_TARGET_HEATER_OFF"

                else:
                    state = "RUNNING_MPC_FAN_TEST"

            with open(log_file, "a", newline="") as file:
                writer = csv.writer(file)
                writer.writerow([
                    elapsed,
                    round(temp_c, 2),
                    TARGET_C,
                    heater_output,
                    MOTOR_ON_SPEED,
                    state
                ])

            print(
                f"{elapsed}s | Temp: {temp_c:.2f} °C | "
                f"Target: {TARGET_C:.1f} °C | "
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

            print(f"Sensor error: {e} | keping same duty: {heater_output:.1f}%")

            state = "SENSOR_ERROR_KEEPING_DUTY"

            with open(log_file, "a", newline="") as file:
                writer = csv.writer(file)
                writer.writerow([
                    elapsed,
                    "NaN",
                    TARGET_C,
                    heater_output,
                    MOTOR_ON_SPEED,
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
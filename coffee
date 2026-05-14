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

HEATER_GPIO = 18
CONTROL_WINDOW_S = 2.0

KP = 4.0
KI = 0.05
KD = 1.5

# L298N motor connections
IN1 = 23
IN2 = 24
ENA = 12
MOTOR_SPEED = 1.0


spi = board.SPI()
cs = digitalio.DigitalInOut(board.D8)
sensor = adafruit_max31855.MAX31855(spi, cs)


# Manual PID variables
integral = 0.0
previous_error = 0.0
previous_time = time.time()


heater = DigitalOutputDevice(HEATER_GPIO, active_high=True, initial_value=False)

motor = Motor(forward=IN1, backward=IN2)
enable = PWMOutputDevice(ENA, frequency=1000)


def fan_on(speed=1.0):
    enable.value = speed
    motor.forward()


def fan_off():
    motor.stop()
    enable.value = 0


def calculate_pid(temp_c):
    global integral, previous_error, previous_time

    current_time = time.time()
    dt = current_time - previous_time

    if dt <= 0:
        dt = 0.001

    error = TARGET_C - temp_c

    integral += error * dt

    derivative = (error - previous_error) / dt

    output = (KP * error) + (KI * integral) + (KD * derivative)

    previous_error = error
    previous_time = current_time

    if output > 100:
        output = 100.0
    elif output < 0:
        output = 0.0

    return output


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


print("Coffee roaster piD + fan control started.")
print(f"Target temperature: {TARGET_C}  C")
print(f"Logging to: {log_file}")
print("Press CTRL+C to stop.")


start_time = time.time()

try:
    fan_on(MOTOR_SPEED)

    while True:
        elapsed = round(time.time() - start_time, 1)

        try:
            temp_c = sensor.temperature

            if temp_c is None:
                raise RuntimeError("No temperature reading")

            heater_output = calculate_pid(temp_c)

            heater_output = round(heater_output, 1)

            if temp_c > MAX_SAFE_TEMP_C:
                heater_output = 0.0
                state = "SAFETY_SHUTDOWN_OVERTEMP"

            elif temp_c > TARGET_C + 15:
                heater_output = 0.0
                state = "ABOVE_TARGET_HEATER_OFF"

            else:
                state = "RUNNING_PID_FAN_TEST"

            with open(log_file, "a", newline="") as file:
                writer = csv.writer(file)
                writer.writerow([
                    elapsed,
                    round(temp_c, 2),
                    TARGET_C,
                    heater_output,
                    MOTOR_SPEED,
                    state
                ])

            print(
                f"{elapsed}s | Temp: {temp_c:.2f}  C | "
                f"Target: {TARGET_C:.1f}  C | "
                f"Heater: {heater_output:.1f}% | "
                f"Fan: {MOTOR_SPEED:.1f} | {state}"
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
            heater.off()
            print(f"Sensor error: {e} | Heater forced to 0%, fan still ON")
            time.sleep(CONTROL_WINDOW_S)

except KeyboardInterrupt:
    heater.off()
    fan_off()
    print("\nHeater OFF. Fan OFF.")
import time
import csv
import os
from datetime import datetime

import board
import digitalio
import adafruit_max31855
from simple_pid import PID
from gpiozero import DigitalOutputDevice, Motor, PWMOutputDevice


TARGET_C = 180.0
MAX_SAFE_TEMP_C = 250.0
LOG_FOLDER = "logs"
COMMAND_FILE = "roaster_command.txt"

HEATER_GPIO = 18
CONTROL_WINDOW_S = 2.0

KP = 4.0
KI = 0
KD = 0

IN1 = 23
IN2 = 24
ENA = 12

# Your circuit is reversed:
# 0.0 = fan ON
# 1.0 = fan OFF
MOTOR_ON_SPEED = 0.0
MOTOR_OFF_SPEED = 1.0


spi = board.SPI()
cs = digitalio.DigitalInOut(board.D8)
sensor = adafruit_max31855.MAX31855(spi, cs)

pid = PID(KP, KI, KD, setpoint=TARGET_C)
pid.output_limits = (0, 100)

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


print("Coffee roaster PID + fan control started.")
print("Dashboard controls: IDLE / RUN / STOP / E_STOP")
print(f"Target temperature: {TARGET_C} °C")
print(f"Logging to: {log_file}")
print("Press CTRL+C to stop.")


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
                heater_output = pid(temp_c)

                if heater_output is None:
                    heater_output = 0.0

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
                    MOTOR_ON_SPEED,
                    state
                ])

            print(
                f"{elapsed}s | Temp: {temp_c:.2f} °C | "
                f"Target: {TARGET_C:.1f} °C | "
                f"Heater: {heater_output:.1f}% | "
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
            heater.off()
            print(f"Sensor error: {e} | Heater forced to 0%, fan still ON")
            time.sleep(CONTROL_WINDOW_S)

except KeyboardInterrupt:
    heater.off()
    fan_off()
    print("\nStopped safely. Heater OFF. Fan OFF.")
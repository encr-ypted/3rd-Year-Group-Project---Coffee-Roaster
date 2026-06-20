import time
import csv
import os
import math
from datetime import datetime

import board
import digitalio
import adafruit_max31855
from gpiozero import DigitalOutputDevice, PWMOutputDevice


TARGET_C = 180.0
MAX_SAFE_TEMP_C = 250.0
LOG_FOLDER = "logs"
COMMAND_FILE = "roaster_command.txt"
DEFAULT_COMMAND = "IDLE"

HEATER_GPIO = 23
CONTROL_WINDOW_S = 1.0

ENA = 12
MOTOR_ON_SPEED = 0.0
MOTOR_OFF_SPEED = 1.0

FAN_START_SPEED = 0.0
FAN_END_SPEED = 0.2
FAN_DECREASE_TIME_S = 550

FAN_RAMP_TIME_S = 1.8
FAN_RAMP_STEPS = 10
fan_ramp_done = False
fan_is_on = False

PREHEAT_TARGET_C = 190
PREHEAT_STABLE_BAND_C = 4.0
PREHEAT_DROP_DETECT_C = 10.0
BEAN_DROP_RISE_CONFIRM_C = 0.3

AMBIENT_C = 25.0
MODEL_A = 0.9978

PREHEAT_MODEL_B = 0.0041
ROAST_MODEL_B = 0.009

MODEL_B_MIN = 0.0035
MODEL_B_MAX = 0.0110
MODEL_B_ADAPT_INTERVAL_S = 8.0
MODEL_B_ADAPT_STEP = 0.00015
MODEL_B_ERROR_THRESHOLD_C = 1.5

PREDICTION_HORIZON = 100
DUTY_STEP = 1

WEIGHT_TRACKING = 20.0
WEIGHT_HEATER_CHG_IN = 0.1
WEIGHT_OVERSHOOT = 15.0

RAMP_MIDPOINT_MIN = 4.5
RAMP_STEEPNESS = 0.75

previous_heater_output = 0.0
roast_start_temp_c = None
current_target_c = TARGET_C
last_setpoint_c = TARGET_C
last_model_b_adapt_time = 0.0

preheat_ready = False
preheat_ready_temp_c = None
bean_drop_started = False
bean_drop_lowest_temp_c = None


spi = board.SPI()
cs = digitalio.DigitalInOut(board.D7)
sensor = adafruit_max31855.MAX31855(spi, cs)

heater = DigitalOutputDevice(HEATER_GPIO, active_high=True, initial_value=False)
enable = PWMOutputDevice(ENA, frequency=1000)


def fan_ramp_to(target_speed):
    global fan_is_on

    print("ramp fan before heater is started")

    start_speed = enable.value

    for i in range(FAN_RAMP_STEPS + 1):
        speed = start_speed - ((start_speed - target_speed) * (i / FAN_RAMP_STEPS))
        enable.value = speed
        print(f"Fan ramp spd: {speed:.2f}")
        time.sleep(FAN_RAMP_TIME_S / FAN_RAMP_STEPS)

    enable.value = target_speed
    fan_is_on = target_speed < MOTOR_OFF_SPEED
    print("Fan ramp complete so heater is now allowed")


def fan_on():
    global fan_is_on

    if not fan_is_on:
        fan_ramp_to(MOTOR_ON_SPEED)
    else:
        enable.value = MOTOR_ON_SPEED


def fan_off():
    global fan_is_on

    enable.value = MOTOR_OFF_SPEED
    fan_is_on = False


def fan_speed_for_roast(elapsed_s):
    progress = min(1.0, max(0.0, elapsed_s / FAN_DECREASE_TIME_S))
    return FAN_START_SPEED + ((FAN_END_SPEED - FAN_START_SPEED) * progress)


def fan_ramp_start():
    fan_ramp_to(MOTOR_ON_SPEED)


def write_command(command):
    with open(COMMAND_FILE, "w") as file:
        file.write(command)


def read_command():
    global current_target_c

    if not os.path.exists(COMMAND_FILE):
        return "IDLE", current_target_c

    with open(COMMAND_FILE, "r") as file:
        text = file.read().strip()

    if text.startswith("RUN,"):
        try:
            _, target = text.split(",")
            current_target_c = float(target)
            return "RUN", current_target_c
        except Exception:
            return "RUN", current_target_c

    if text.startswith("PREHEAT,"):
        try:
            _, target = text.split(",")
            current_target_c = float(target)
            return "PREHEAT", current_target_c
        except Exception:
            return "PREHEAT", current_target_c

    return text, current_target_c


def setpoint_curve(start_temp_c, target_c, elapsed_s, midpoint_min, steepness):
    start = float(start_temp_c)
    target = float(target_c)
    midpoint_min = float(midpoint_min)
    steepness = float(steepness)

    if target <= start:
        return target

    t_min = max(0.0, float(elapsed_s)) / 60.0

    raw_zero = (target - start) / (1.0 + math.exp(-steepness * (0.0 - midpoint_min))) + start
    raw_now = (target - start) / (1.0 + math.exp(-steepness * (t_min - midpoint_min))) + start

    setpoint = start + ((raw_now - raw_zero) / (target - raw_zero)) * (target - start)

    return min(setpoint, target)


def calculate_mpc(temp_c, target_c, elapsed_s=None, roast_start_temp_c=None, model_b=None):
    global previous_heater_output

    if model_b is None:
        model_b = ROAST_MODEL_B

    best_duty = 0.0
    best_cost = float("inf")

    for duty in range(0, 101, DUTY_STEP):
        predicted_temp = temp_c
        cost = 0.0

        for step in range(PREDICTION_HORIZON):
            predicted_temp = (
                AMBIENT_C
                + MODEL_A * (predicted_temp - AMBIENT_C)
                + model_b * duty
            )

            if elapsed_s is not None and roast_start_temp_c is not None:
                future_setpoint = setpoint_curve(
                    roast_start_temp_c,
                    target_c,
                    elapsed_s + step,
                    RAMP_MIDPOINT_MIN,
                    RAMP_STEEPNESS
                )
            else:
                future_setpoint = target_c

            error = future_setpoint - predicted_temp
            cost += WEIGHT_TRACKING * (error ** 2)

            if predicted_temp > future_setpoint + 5:
                cost += WEIGHT_OVERSHOOT * ((predicted_temp - future_setpoint) ** 2)

            if predicted_temp > MAX_SAFE_TEMP_C:
                cost += 100000

        cost += WEIGHT_HEATER_CHG_IN * ((duty - previous_heater_output) ** 2)

        if cost < best_cost:
            best_cost = cost
            best_duty = duty

    previous_heater_output = best_duty
    return float(best_duty)


def adapt_model_b(temp_c, setpoint_c, elapsed_s):
    global ROAST_MODEL_B
    global last_model_b_adapt_time

    if elapsed_s - last_model_b_adapt_time < MODEL_B_ADAPT_INTERVAL_S:
        return

    error = setpoint_c - temp_c

    if error > MODEL_B_ERROR_THRESHOLD_C:
        ROAST_MODEL_B = max(MODEL_B_MIN, ROAST_MODEL_B - MODEL_B_ADAPT_STEP)
        last_model_b_adapt_time = elapsed_s

    elif error < -MODEL_B_ERROR_THRESHOLD_C:
        ROAST_MODEL_B = min(MODEL_B_MAX, ROAST_MODEL_B + MODEL_B_ADAPT_STEP)
        last_model_b_adapt_time = elapsed_s


os.makedirs(LOG_FOLDER, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = f"{LOG_FOLDER}/roast_{timestamp}.csv"

with open(log_file, "w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow([
        "time_s",
        "temp_c",
        "target_c",
        "setpoint_c",
        "start_temp_c",
        "ramp_midpoint_min",
        "ramp_steepness",
        "model_b",
        "heater_output_percent",
        "fan_speed",
        "state"
    ])


print(f"Default target temperature: {TARGET_C} °C")
print(f"Logging to: {log_file}")


write_command(DEFAULT_COMMAND)


start_time = time.time()
last_command = "IDLE"

try:
    
    fan_off()
    fan_ramp_start()
    fan_ramp_done = True
    while True:
        elapsed = round(time.time() - start_time, 1)
        command, target_c = read_command()
        active_model_b = ROAST_MODEL_B

        try:
            temp_c = sensor.temperature

            if temp_c is None:
                raise RuntimeError("No temperature reading")

            if command == "E_STOP":
                heater.off()
                fan_on()
                print("EMERGENCY STOP from dashboard")
                break

            setpoint_c = last_setpoint_c

            if preheat_ready and preheat_ready_temp_c is not None:
                if not bean_drop_started:
                    if temp_c < preheat_ready_temp_c - PREHEAT_DROP_DETECT_C:
                        bean_drop_started = True
                        bean_drop_lowest_temp_c = temp_c
                        state = "BEAN_DROP_DETECTED_WAITING_FOR_BOTTOM"

                else:
                    if temp_c < bean_drop_lowest_temp_c:
                        bean_drop_lowest_temp_c = temp_c

                    if temp_c >= bean_drop_lowest_temp_c + BEAN_DROP_RISE_CONFIRM_C:
                        command = "RUN"
                        write_command(f"RUN,{target_c}")
                        start_time = time.time()
                        elapsed = 0.0
                        roast_start_temp_c = bean_drop_lowest_temp_c
                        last_setpoint_c = bean_drop_lowest_temp_c
                        setpoint_c = bean_drop_lowest_temp_c
                        last_model_b_adapt_time = 0.0
                        preheat_ready = False
                        bean_drop_started = False

            if command == "RUN" and last_command != "RUN":
                if roast_start_temp_c is None:
                    start_time = time.time()
                    elapsed = 0.0
                    roast_start_temp_c = temp_c
                    last_model_b_adapt_time = 0.0

            if command == "IDLE":
                heater_output = 0.0

                if temp_c < 45.0:
                    fan_off()
                else:
                    fan_on()

                state = "IDLE"

            elif command == "FAN_TEST":
                heater_output = 0.0
                fan_on()
                state = "IDLE"
            
            elif command == "PREHEAT":
                fan_on()
                active_model_b = PREHEAT_MODEL_B

                if bean_drop_started:
                    setpoint_c = temp_c
                    heater_output = calculate_mpc(
                        temp_c,
                        setpoint_c,
                        model_b=PREHEAT_MODEL_B
                    )
                    heater_output = round(heater_output, 1)
                    state = "BEAN_DROP_DETECTED_WAITING_FOR_BOTTOM"

                else:
                    setpoint_c = PREHEAT_TARGET_C
                    heater_output = calculate_mpc(
                        temp_c,
                        setpoint_c,
                        model_b=PREHEAT_MODEL_B
                    )
                    heater_output = round(heater_output, 1)

                    if abs(temp_c - PREHEAT_TARGET_C) <= PREHEAT_STABLE_BAND_C:
                        preheat_ready = True
                        preheat_ready_temp_c = temp_c
                        state = "PREHEAT_READY_ADD_BEANS"
                    else:
                        state = "PREHEATING"


            elif command == "STOP":
                heater_output = 0.0

                if temp_c < 45.0:
                    fan_off()
                    time.sleep(5)
                    state = "IDLE"
                else:
                    fan_on()
                    state = "COOLING_FROM_DASHBOARD"

            else:
                if roast_start_temp_c is None:
                    roast_start_temp_c = temp_c

                fan_speed = fan_speed_for_roast(elapsed)

                if not fan_is_on:
                    fan_ramp_to(fan_speed)
                else:
                    enable.value = fan_speed

                setpoint_c = setpoint_curve(
                    roast_start_temp_c,
                    target_c,
                    elapsed,
                    RAMP_MIDPOINT_MIN,
                    RAMP_STEEPNESS
                )

                last_setpoint_c = setpoint_c
                active_model_b = ROAST_MODEL_B

                heater_output = calculate_mpc(
                    temp_c,
                    target_c,
                    elapsed,
                    roast_start_temp_c,
                    model_b=ROAST_MODEL_B
                )
                heater_output = round(heater_output, 1)

                adapt_model_b(temp_c, setpoint_c, elapsed)

                active_model_b = ROAST_MODEL_B

                if temp_c > MAX_SAFE_TEMP_C:
                    heater_output = 0.0
                    state = "SAFETY_SHUTDOWN_OVERTEMP"

                elif temp_c > setpoint_c + 15:
                    heater_output = 0.0
                    state = "ABOVE_TARGET_HEATER_OFF"

                else:
                    state = "RUNNING_MPC_FAN_TEST"

            last_command = command

            
            if not fan_ramp_done and command not in ["IDLE", "FAN_TEST", "STOP"]:
                heater_output = 0.0
                state = "WAITING_FOR_FAN_RAMP"
            

            with open(log_file, "a", newline="") as file:
                writer = csv.writer(file)
                writer.writerow([
                    elapsed,
                    round(temp_c, 2),
                    target_c,
                    round(setpoint_c, 2),
                    round(roast_start_temp_c, 2) if roast_start_temp_c is not None else "",
                    RAMP_MIDPOINT_MIN,
                    RAMP_STEEPNESS,
                    round(active_model_b, 6),
                    heater_output,
                    enable.value,
                    state
                ])

            actual_fan_percent = (1.0 - enable.value) * 100

            print(
                f"{elapsed}s | Temp: {temp_c:.2f} °C | "
                f"Target: {target_c:.1f} °C | "
                f"Setpoint: {setpoint_c:.1f} °C | "
                f"MPC Heater: {heater_output:.1f}% | "
                f"Fan: {actual_fan_percent:.1f}% | "
                f"Model B: {active_model_b:.6f} | {state}"
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

            print(f"Sensor error: {e} so keeping same duty: {heater_output:.1f}%")

            state = "SENSOR_ERROR_KEEPING_DUTY"

            with open(log_file, "a", newline="") as file:
                writer = csv.writer(file)
                writer.writerow([
                    elapsed,
                    "NaN",
                    target_c,
                    round(last_setpoint_c, 2),
                    round(roast_start_temp_c, 2) if roast_start_temp_c is not None else "",
                    RAMP_MIDPOINT_MIN,
                    RAMP_STEEPNESS,
                    round(active_model_b, 6),
                    heater_output,
                    enable.value,
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
    print("\nStopped . Heater OFF. Fan OFF.")
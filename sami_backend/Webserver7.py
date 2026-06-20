import asyncio
import csv
import glob
import json
import os
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn


app = FastAPI()
clients = []

COMMAND_FILE = "roaster_command.json"
last_target_c = 210.0
last_profile_id = "medium"
fan_test_on = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


ROAST_PROFILES = [
    {"id": "light", "name": "Light", "desc": "Fruity & bright", "target_c": 196.0, "ramp_midpoint_min": 2.0, "ramp_steepness": 1.0},
    {"id": "medium", "name": "Medium", "desc": "Balanced & smooth", "target_c": 210.0, "ramp_midpoint_min": 2.0, "ramp_steepness": 1.0},
    {"id": "medium-dark", "name": "Medium-Dark", "desc": "Rich & full-bodied", "target_c": 220.0, "ramp_midpoint_min": 2.0, "ramp_steepness": 1.0},
    {"id": "dark", "name": "Dark", "desc": "Bold & smoky", "target_c": 230.0, "ramp_midpoint_min": 2.0, "ramp_steepness": 1.0},
]


@app.get("/api/profiles")
async def api_profiles():
    return {"profiles": ROAST_PROFILES}


def write_command(command, **params):
    payload = {
        "id": time.time_ns(),
        "command": command,
        **params,
    }

    tmp_file = COMMAND_FILE + ".tmp"

    with open(tmp_file, "w") as file:
        json.dump(payload, file)
        file.flush()
        os.fsync(file.fileno())

    os.replace(tmp_file, COMMAND_FILE)


def get_profile_target(profile_id):
    profile = next(
        (p for p in ROAST_PROFILES if p["id"] == profile_id),
        ROAST_PROFILES[1]
    )
    return profile["target_c"]


def get_latest_log_file():
    files = glob.glob("logs/roast_*.csv")
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def safe_float(value, default=0.0):
    try:
        if value in ["", None, "NaN"]:
            return default
        return float(value)
    except Exception:
        return default


def safe_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ["true", "1", "yes", "y"]


def map_state_for_frontend(state):
    if state == "IDLE":
        return "IDLE"

    if state in [
        "PREHEATING",
        "PREHEAT_READY_ADD_BEANS",
        "BEAN_DROP_DETECTED_WAITING_FOR_BOTTOM",
    ]:
        return "PREHEAT"

    if state in [
        "RUNNING_MPC_FAN_TEST",
        "ABOVE_TARGET_HEATER_OFF",
        "SENSOR_ERROR_KEEPING_DUTY",
        "START_ROAST_SENT",
    ]:
        return "ROASTING"

    if state in [
        "COOLING_FROM_DASHBOARD",
        "STOP_AND_COOL_SENT",
    ]:
        return "COOLING"

    if state in [
        "SAFETY_SHUTDOWN_OVERTEMP",
        "E_STOP",
        "ERROR",
        "EMERGENCY_STOP_SENT",
    ]:
        return "ERROR"

    return state


def get_latest_row():
    log_file = get_latest_log_file()

    if log_file is None:
        return {
            "type": "telemetry",
            "timestamp": 0,
            "temp": 0,
            "target": last_target_c,
            "setpoint": last_target_c,
            "start_temp": 0,
            "ramp_midpoint_min": 2.0,
            "ramp_steepness": 1.0,
            "ror": 0,
            "heater_pwm": 0,
            "fan_pwm": 0,
            "grayscale": None,
            "grayscale_done_threshold": 115.0,
            "roast_done": False,
            "state": "IDLE",
            "raw_state": "IDLE",
            "heater_halted": False,
            "can_resume": False,
            "sensor_fault": None,
            "test_spin": False,
        }

    try:
        with open(log_file, "r") as file:
            rows = list(csv.DictReader(file))

        if len(rows) == 0:
            raise RuntimeError("No CSV rows")

        latest = rows[-1]
        raw_state = latest.get("state", "UNKNOWN")
        frontend_state = map_state_for_frontend(raw_state)

        sensor_fault = None
        if raw_state == "SENSOR_ERROR_KEEPING_DUTY":
            sensor_fault = "Sensor fault, keeping previous duty"

        raw_fan = safe_float(latest.get("fan_speed", 1.0))
        fan_pwm = (1.0 - raw_fan) * 100
        roast_done = safe_bool(latest.get("roast_done"), False)

        return {
            "type": "telemetry",
            "timestamp": safe_float(latest.get("time_s", 0)),
            "temp": safe_float(latest.get("temp_c", 0)),
            "target": safe_float(latest.get("target_c", last_target_c)),
            "setpoint": safe_float(latest.get("setpoint_c", latest.get("target_c", last_target_c))),
            "start_temp": safe_float(latest.get("start_temp_c", 0)),
            "ramp_midpoint_min": safe_float(latest.get("ramp_midpoint_min", 2.0)),
            "ramp_steepness": safe_float(latest.get("ramp_steepness", 1.0)),
            "ror": 0,
            "heater_pwm": safe_float(latest.get("heater_output_percent", 0)),
            "fan_pwm": fan_pwm,
            "grayscale": safe_float(latest.get("mean_grayscale", None), None),
            "grayscale_done_threshold": safe_float(latest.get("grayscale_done_threshold", 115.0), 115.0),
            "roast_done": roast_done,
            "state": frontend_state,
            "raw_state": raw_state,
            "heater_halted": False,
            "can_resume": frontend_state == "COOLING",
            "sensor_fault": sensor_fault,
            "test_spin": False,
        }

    except Exception as e:
        return {"type": "error", "msg": str(e)}


async def broadcaster():
    while True:
        message = get_latest_row()
        for ws in list(clients):
            try:
                await ws.send_json(message)
            except Exception:
                if ws in clients:
                    clients.remove(ws)

        await asyncio.sleep(1)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(broadcaster())


@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    global last_target_c
    global last_profile_id
    global fan_test_on

    await websocket.accept()
    clients.append(websocket)

    try:
        await websocket.send_json({
            "type": "system_state",
            "state": "IDLE",
        })

        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "GET_STATE":
                latest = get_latest_row()
                await websocket.send_json({
                    "type": "system_state",
                    "state": latest.get("state", "IDLE"),
                    "raw_state": latest.get("raw_state", latest.get("state", "IDLE")),
                })

            elif action == "START_ROAST":
                profile_id = data.get("profile_id", "medium")
                last_profile_id = profile_id
                last_target_c = get_profile_target(profile_id)

                write_command("PREHEAT", target_c=last_target_c, profile_id=profile_id)

                await websocket.send_json({
                    "type": "roast_action",
                    "action": action,
                    "ok": True,
                    "state": "PREHEAT",
                })

            elif action == "STOP_ROAST":
                write_command("STOP")
                await websocket.send_json({
                    "type": "roast_action",
                    "action": action,
                    "ok": True,
                    "state": "COOLING",
                })

            elif action == "RESUME_ROAST":
                write_command("RUN", target_c=last_target_c, profile_id=last_profile_id)
                await websocket.send_json({
                    "type": "roast_action",
                    "action": action,
                    "ok": True,
                    "state": "ROASTING",
                })

            elif action == "FINISH_ROAST":
                write_command("STOP")
                await websocket.send_json({
                    "type": "roast_action",
                    "action": action,
                    "ok": True,
                    "state": "COOLING",
                })

            elif action == "E_STOP":
                write_command("E_STOP")
                await websocket.send_json({
                    "type": "roast_action",
                    "action": action,
                    "ok": True,
                    "state": "ERROR",
                })

            elif action == "TEST_SPIN":
                fan_test_on = not fan_test_on

                if fan_test_on:
                    write_command("FAN_TEST")
                    test_spin = True
                    fan_pwm = 100
                else:
                    write_command("IDLE")
                    test_spin = False
                    fan_pwm = 0

                await websocket.send_json({
                    "type": "roast_action",
                    "action": action,
                    "ok": True,
                    "test_spin": test_spin,
                    "fan_pwm": fan_pwm,
                    "state": "IDLE",
                })

            elif action == "HEATER_CLEAR_HALT":
                await websocket.send_json({
                    "type": "heater_status",
                    "heater_halted": False,
                })

    except WebSocketDisconnect:
        if websocket in clients:
            clients.remove(websocket)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

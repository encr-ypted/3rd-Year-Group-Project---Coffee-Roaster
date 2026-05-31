import asyncio
import csv
import glob
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn


app = FastAPI()
clients = []

COMMAND_FILE = "roaster_command.txt"


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


ROAST_PROFILES = [
    {
        "id": "light",
        "name": "Light",
        "desc": "Fruity & bright",
        "target_c": 196.0,
    },
    {
        "id": "medium",
        "name": "Medium",
        "desc": "Balanced & smooth",
        "target_c": 210.0,
    },
    {
        "id": "medium-dark",
        "name": "Medium-Dark",
        "desc": "Rich & full-bodied",
        "target_c": 220.0,
    },
    {
        "id": "dark",
        "name": "Dark",
        "desc": "Bold & smoky",
        "target_c": 230.0,
    },
]


@app.get("/api/profiles")
async def api_profiles():
    return {"profiles": ROAST_PROFILES}


def write_command(command):
    with open(COMMAND_FILE, "w") as file:
        file.write(command)


def get_latest_log_file():
    files = glob.glob("logs/roast_*.csv")

    if not files:
        return None

    return max(files, key=os.path.getmtime)


def get_latest_row():
    log_file = get_latest_log_file()

    if log_file is None:
        return {
            "type": "telemetry",
            "timestamp": 0,
            "temp": 0,
            "target": 0,
            "ror": 0,
            "heater_pwm": 0,
            "fan_pwm": 0,
            "state": "NO_LOG_FILE",
            "heater_halted": False,
        }

    try:
        with open(log_file, "r") as file:
            rows = list(csv.DictReader(file))

        if len(rows) == 0:
            raise RuntimeError("No CSV rows")

        latest = rows[-1]

        temp_raw = latest.get("temp_c", 0)

        try:
            temp = float(temp_raw)
        except Exception:
            temp = 0.0

        return {
            "type": "telemetry",
            "timestamp": float(latest.get("time_s", 0)),
            "temp": temp,
            "target": float(latest.get("target_c", 0)),
            "ror": 0,
            "heater_pwm": float(latest.get("heater_output_percent", 0)),
            "fan_pwm": float(latest.get("fan_speed", 0)) * 100,
            "state": latest.get("state", "UNKNOWN"),
            "heater_halted": False,
        }

    except Exception as e:
        return {
            "type": "error",
            "msg": str(e),
        }


async def broadcaster():
    while True:
        message = get_latest_row()

        for ws in list(clients):
            try:
                await ws.send_json(message)
            except Exception:
                clients.remove(ws)

        await asyncio.sleep(1)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(broadcaster())


@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.append(websocket)

    try:
        await websocket.send_json({
            "type": "system_state",
            "state": "CONNECTED_TO_CSV_BRIDGE",
        })

        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "GET_STATE":
                await websocket.send_json({
                    "type": "system_state",
                    "state": "CSV_BRIDGE_RUNNING",
                })

            elif action == "START_ROAST":
                write_command("RUN")
                await websocket.send_json({
                    "type": "system_state",
                    "state": "START_ROAST_SENT",
                })

            elif action == "STOP_ROAST":
                write_command("STOP")
                await websocket.send_json({
                    "type": "system_state",
                    "state": "STOP_AND_COOL_SENT",
                })

            elif action == "E_STOP":
                write_command("E_STOP")
                await websocket.send_json({
                    "type": "system_state",
                    "state": "EMERGENCY_STOP_SENT",
                })

            elif action == "HEATER_CLEAR_HALT":
                await websocket.send_json({
                    "type": "heater_status",
                    "heater_halted": False,
                })

    except WebSocketDisconnect:
        clients.remove(websocket)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
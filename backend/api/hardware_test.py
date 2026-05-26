"""

Hardware bench API — separate from the roast WebSocket.



Run on the Pi (do not run api/main.py at the same time):

    python api/hardware_test.py



WebSocket:  ws://127.0.0.1:8001/ws/bench

REST:       http://127.0.0.1:8001/api/bench/...

"""



import asyncio

import os

import sys

from contextlib import asynccontextmanager



from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from fastapi.middleware.cors import CORSMiddleware

import uvicorn



sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))



from hardware.pid import PIDController
from hardware.test_bench import HardwareTestBench



BENCH_PORT = 8001



bench = HardwareTestBench()

active_connections: list[WebSocket] = []





@asynccontextmanager

async def lifespan(app: FastAPI):

    await bench.start()

    asyncio.create_task(_broadcaster())

    yield

    bench.shutdown()





app = FastAPI(title="Coffee Roaster Hardware Bench", lifespan=lifespan)

app.add_middleware(

    CORSMiddleware,

    allow_origins=["*"],

    allow_credentials=True,

    allow_methods=["*"],

    allow_headers=["*"],

)





async def _broadcast(message: dict) -> None:

    for ws in list(active_connections):

        try:

            await ws.send_json(message)

        except Exception:

            active_connections.remove(ws)





async def _broadcaster() -> None:

    while True:

        data = await bench.message_queue.get()

        await _broadcast(data)

        bench.message_queue.task_done()





def _handle_action(action: str, data: dict) -> dict:

    if action == "SESSION_START":

        bench.start_session()

        return {"ok": True, "session_active": True}

    if action == "SESSION_STOP":

        bench.stop_session()

        return {"ok": True, "session_active": False, "pid_active": False}

    if action == "E_STOP":

        bench.emergency_stop()

        return {"ok": True, "session_active": False, "pid_active": False}

    if action == "READ_SENSORS":

        sensors = bench.read_sensors()

        t = bench.telemetry_payload()

        return {

            "ok": True,

            "sensors": sensors,

            "temp": t["temp"],

            "heater_pwm": t["heater_pwm"],

            "fan_pwm": t["fan_pwm"],

            "session_active": t["session_active"],

            "pid_active": t["pid_active"],

            "pid_target": t["pid_target"],

        }

    if action == "FAN_SET":

        pwm = bench.set_fan(float(data.get("percent", 0)))

        return {"ok": True, "fan_pwm": pwm}

    if action == "FAN_STOP":

        bench.stop_fan()

        return {"ok": True, "fan_pwm": 0}

    if action in ("HEAT_TO_TARGET", "HEATER_PID_START"):

        target = bench.heat_to_target(float(data.get("target_temp", 100)))

        return {

            "ok": True,

            "session_active": True,

            "pid_active": True,

            "pid_target": target,

            "heater_mode": "ramp",

            "note": "Full power until near target, then PID",

        }

    if action in ("HEAT_STOP", "HEATER_PID_STOP"):

        bench.stop_heating()

        return {"ok": True, "pid_active": False, "heater_pwm": 0}

    if action in ("SET_TARGET", "HEATER_PID_SET_TARGET"):

        target = bench.set_target(float(data.get("target_temp", bench.pid_target)))

        return {"ok": True, "pid_target": target}

    if action == "GET_PID_GAINS":
        gains = bench.pid_gains()
        return {
            "ok": True,
            **gains,
            "pid_kp": gains["kp"],
            "pid_ki": gains["ki"],
            "pid_kd": gains["kd"],
            "defaults": PIDController.default_gains(),
        }

    if action == "SET_PID_GAINS":
        gains = bench.set_pid_gains(
            float(data["kp"]) if "kp" in data else None,
            float(data["ki"]) if "ki" in data else None,
            float(data["kd"]) if "kd" in data else None,
            reset=bool(data.get("reset_integral", False)),
        )
        return {
            "ok": True,
            **gains,
            "pid_kp": gains["kp"],
            "pid_ki": gains["ki"],
            "pid_kd": gains["kd"],
            "note": "PID gains updated (live on bench)",
        }

    return {"ok": False, "error": f"Unknown action: {action}"}





@app.get("/api/bench/status")

async def bench_status():

    return {"ok": True, **bench.read_sensors(), **bench.telemetry_payload()}





async def _send_telemetry(websocket: WebSocket) -> None:

    try:

        bench.read_sensors()

        await websocket.send_json(bench.telemetry_payload())

    except Exception as exc:

        await websocket.send_json(

            {

                "type": "bench_telemetry",

                "temp": None,

                "sensor_fault": str(exc),

                "heater_pwm": bench.heater_pwm,

                "fan_pwm": bench.fan_pwm,

                "session_active": bench.session_active,

            }

        )





@app.websocket("/ws/bench")

async def bench_websocket(websocket: WebSocket):

    await websocket.accept()

    active_connections.append(websocket)

    try:

        gains = bench.pid_gains()
        await websocket.send_json(
            {
                "type": "bench_ready",
                "msg": "Set a target and use Heat to target.",
                **gains,
                "pid_kp": gains["kp"],
                "pid_ki": gains["ki"],
                "pid_kd": gains["kd"],
                "pid_defaults": PIDController.default_gains(),
            }
        )

        await _send_telemetry(websocket)

        while True:

            data = await websocket.receive_json()

            action = data.get("action", "")

            result = _handle_action(action, data)

            await websocket.send_json({"type": "bench_result", "action": action, **result})

    except WebSocketDisconnect:

        active_connections.remove(websocket)





if __name__ == "__main__":

    uvicorn.run(app, host="0.0.0.0", port=BENCH_PORT)



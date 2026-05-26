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
        return {"ok": True, "session_active": False}
    if action == "E_STOP":
        bench.emergency_stop()
        return {"ok": True, "session_active": False}
    if action == "READ_SENSORS":
        sensors = bench.read_sensors()
        t = bench.telemetry_payload()
        return {
            "ok": True,
            "sensors": sensors,
            "temp": t["temp"],
            "temp_raw": t["temp_raw"],
            "heater_pwm": t["heater_pwm"],
            "fan_pwm": t["fan_pwm"],
            "session_active": t["session_active"],
        }
    if action == "FAN_SET":
        pwm = bench.set_fan(float(data.get("percent", 0)))
        return {"ok": True, "fan_pwm": pwm}
    if action == "FAN_STOP":
        bench.stop_fan()
        return {"ok": True, "fan_pwm": 0}
    if action == "HEATER_ON":
        bench.heater_on()
        return {"ok": True, "heater_pwm": 100}
    if action == "HEATER_OFF":
        bench.heater_off()
        return {"ok": True, "heater_pwm": 0}
    if action == "HEATER_PULSE":
        percent = float(data.get("percent", 0))
        bench.heater_pulse(percent)
        return {
            "ok": True,
            "heater_pwm": round(percent, 1),
            "note": "One 2s time-proportional window started",
        }
    return {"ok": False, "error": f"Unknown action: {action}"}


@app.get("/api/bench/status")
async def bench_status():
    return {"ok": True, **bench.read_sensors()}


async def _send_telemetry(websocket: WebSocket) -> None:
    bench.read_sensors()
    await websocket.send_json(bench.telemetry_payload())


@app.websocket("/ws/bench")
async def bench_websocket(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        await websocket.send_json(
            {
                "type": "bench_ready",
                "msg": "Live temperature stream active (~2 Hz). Start a session to control outputs.",
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

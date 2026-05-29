"""
Hardware bench API — port 8001. Separate from roast api/main.py.

Run on Pi:  python api/hardware_test.py
WebSocket:  ws://<pi>:8001/ws/bench
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config as cfg
from hardware.manual_control import HardwareTestBench

PORT = 8001
bench = HardwareTestBench()
clients: list[WebSocket] = []


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await bench.run()
    asyncio.create_task(_relay())
    yield
    bench.close()


app = FastAPI(title="Hardware Bench", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _relay() -> None:
    while True:
        msg = await bench.telemetry_queue.get()
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in clients:
                clients.remove(ws)
        bench.telemetry_queue.task_done()


def _dispatch(action: str, body: dict) -> dict:
    if action == "FAN_SET":
        pwm = bench.set_fan(float(body.get("percent", 0)))
        return {"ok": True, "fan_pwm": pwm, **bench.snapshot()}

    if action == "FAN_OFF":
        bench.fan_off()
        return {"ok": True, "fan_pwm": 0, **bench.snapshot()}

    if action == "HEAT_START":
        target = bench.start_heat(float(body.get("target", 100)))
        return {"ok": True, "target": target, "heating": True, **bench.snapshot()}

    if action in ("HEAT_STOP", "E_STOP"):
        bench.stop_heat()
        return {"ok": True, "heating": False, **bench.snapshot()}

    if action == "HEAT_SET_TARGET":
        target = bench.set_target(float(body.get("target", bench.target_c)))
        return {"ok": True, "target": target, **bench.snapshot()}

    if action == "PID_SET":
        g = bench.set_pid(
            float(body["kp"]) if "kp" in body else None,
            float(body["ki"]) if "ki" in body else None,
            float(body["kd"]) if "kd" in body else None,
            reset=bool(body.get("reset_integral", False)),
        )
        return {"ok": True, "pid_kp": g["kp"], "pid_ki": g["ki"], "pid_kd": g["kd"], **bench.snapshot()}

    if action == "GET_STATUS":
        return {
            "ok": True,
            **bench.snapshot(),
            "defaults": {"kp": cfg.PID_KP, "ki": cfg.PID_KI, "kd": cfg.PID_KD},
        }

    return {"ok": False, "error": f"Unknown action: {action}"}


@app.get("/api/bench/status")
async def http_status():
    bench._poll_temp()
    return bench.snapshot()


@app.websocket("/ws/bench")
async def ws_bench(ws: WebSocket):
    await ws.accept()
    clients.append(ws)
    try:
        bench._poll_temp()
        g = bench.pid.get_pid_config()
        await ws.send_json(
            {
                "type": "bench_ready",
                "pid_kp": g["kp"],
                "pid_ki": g["ki"],
                "pid_kd": g["kd"],
                "defaults": {"kp": cfg.PID_KP, "ki": cfg.PID_KI, "kd": cfg.PID_KD},
                **bench.snapshot(),
            }
        )
        while True:
            body = await ws.receive_json()
            action = body.get("action", "")
            result = _dispatch(action, body)
            await ws.send_json({"type": "bench_ack", "action": action, **result})
    except WebSocketDisconnect:
        pass
    finally:
        if ws in clients:
            clients.remove(ws)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)

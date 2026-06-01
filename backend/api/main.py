import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config as cfg
from hardware.controller import RoasterController
from hardware.roast_logger import list_sessions

hw_manager = RoasterController()

active_connections = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    await hw_manager.start()
    asyncio.create_task(_broadcaster())
    yield
    hw_manager.shutdown()


app = FastAPI(title="Smart Coffee Roaster API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _broadcast(message):
    for ws in list(active_connections):
        try:
            await ws.send_json(message)
        except Exception:
            active_connections.remove(ws)


async def _broadcaster():
    while True:
        data = await hw_manager.telemetry_queue.get()
        await _broadcast(data)
        hw_manager.telemetry_queue.task_done()


@app.get("/api/profiles")
async def api_roast_profiles():
    return {"profiles": cfg.list_roast_profiles()}


@app.get("/api/roasts")
async def api_list_roasts():
    return {"log_folder": cfg.LOG_FOLDER, "sessions": list_sessions()}


@app.get("/api/roasts/{roast_id}")
async def api_roast_meta(roast_id: str):
    meta_path = os.path.join(cfg.LOG_FOLDER, f"roast_{roast_id}_meta.json")
    if not os.path.isfile(meta_path):
        return {"ok": False, "error": "not found"}
    with open(meta_path, encoding="utf-8") as f:
        return {"ok": True, "meta": json.load(f)}


@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "START_ROAST":
                hw_manager.start_roast(data.get("profile_id", "default"))
            elif action == "STOP_ROAST":
                hw_manager.stop_roast()
            elif action == "RESUME_ROAST":
                ok = hw_manager.resume_roast()
                await websocket.send_json(
                    {"type": "roast_action", "action": action, "ok": ok}
                )
            elif action == "FINISH_ROAST":
                ok = hw_manager.finish_roast()
                await websocket.send_json(
                    {"type": "roast_action", "action": action, "ok": ok}
                )
            elif action == "E_STOP":
                hw_manager.emergency_stop()
            elif action in ("TEST_SPIN", "TEST_SPIN_START", "TEST_SPIN_STOP"):
                if action == "TEST_SPIN":
                    enable = data.get("enable")
                    if enable is None:
                        enable = not hw_manager._test_spin_active
                    ok = (
                        hw_manager.start_test_spin()
                        if enable
                        else hw_manager.stop_test_spin()
                    )
                    action = "TEST_SPIN"
                elif action == "TEST_SPIN_START":
                    ok = hw_manager.start_test_spin()
                else:
                    ok = hw_manager.stop_test_spin()
                await websocket.send_json(
                    {
                        "type": "roast_action",
                        "action": action,
                        "ok": ok,
                        "test_spin": hw_manager._test_spin_active,
                        "fan_pwm": hw_manager.fan_pwm,
                        "state": hw_manager.state,
                    }
                )
            elif action == "HEATER_CLEAR_HALT":
                hw_manager.clear_heater_halt()
                await websocket.send_json(
                    {
                        "type": "heater_status",
                        "heater_halted": hw_manager._heater.halted,
                    }
                )
            elif action == "GET_STATE":
                await websocket.send_json(
                    {"type": "system_state", "state": hw_manager.state}
                )
    except WebSocketDisconnect:
        active_connections.remove(websocket)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

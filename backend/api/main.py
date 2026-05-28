import asyncio
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hardware.controller import RoasterController

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
            elif action == "E_STOP":
                hw_manager.emergency_stop()
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

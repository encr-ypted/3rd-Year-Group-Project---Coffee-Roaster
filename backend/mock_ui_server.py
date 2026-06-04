#!/usr/bin/env python3
"""
Temporary UI mock — no pip installs (stdlib only). Delete when you have the Pi.

  python mock_ui_server.py

Listens on 0.0.0.0:8000 with:
  GET  /api/profiles
  GET  /api/bench/status
  WS   /ws/telemetry   (main dashboard)
  WS   /ws/bench       (hardware bench page)

Frontend uses HOST "coffee:8000" — on this PC either:
  - Add to hosts file:  127.0.0.1 coffee
  - Or set HOST to localhost:8000 in useCoffeeRoaster.js / useHardwareTest.js
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import random
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HOST = "0.0.0.0"
PORT = 8000
TICK_S = 0.5
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# --- profiles (mirror config.py order) ---
PROFILES = [
    {
        "id": "light",
        "name": "Light",
        "target_c": 196.0,
        "ramp_midpoint_min": 2.5,
        "ramp_steepness": 0.9,
        "desc": "Fruity & bright",
    },
    {
        "id": "medium",
        "name": "Medium",
        "target_c": 210.0,
        "ramp_midpoint_min": 2.0,
        "ramp_steepness": 1.0,
        "desc": "Balanced & smooth",
    },
    {
        "id": "medium-dark",
        "name": "Med-Dark",
        "target_c": 220.0,
        "ramp_midpoint_min": 1.8,
        "ramp_steepness": 1.1,
        "desc": "Rich & full-bodied",
    },
    {
        "id": "dark",
        "name": "Dark",
        "target_c": 230.0,
        "ramp_midpoint_min": 1.6,
        "ramp_steepness": 1.2,
        "desc": "Bold & smoky",
    },
]

PROFILE_BY_ID = {p["id"]: p for p in PROFILES}
PROFILE_BY_ID["default"] = PROFILE_BY_ID["medium"]


def sigmoid_setpoint(start, target, elapsed_s, midpoint_min, steepness):
    if target <= start:
        return target
    t_min = max(0.0, elapsed_s) / 60.0
    span = target - start
    ramped = span / (1.0 + math.exp(-steepness * (t_min - midpoint_min))) + start
    return min(ramped, target)


def ws_accept_key(key: str) -> str:
    digest = hashlib.sha1((key + WS_GUID).encode()).digest()
    return base64.b64encode(digest).decode()


def ws_send_text(conn, text: str) -> None:
    payload = text.encode("utf-8")
    n = len(payload)
    if n < 126:
        header = struct.pack("!BB", 0x81, n)
    elif n < 65536:
        header = struct.pack("!BBH", 0x81, 126, n)
    else:
        header = struct.pack("!BBQ", 0x81, 127, n)
    conn.sendall(header + payload)


def ws_recv_text(conn) -> str | None:
    try:
        hdr = _read_exact(conn, 2)
    except (ConnectionError, OSError):
        return None
    if not hdr:
        return None
    b1, b2 = hdr[0], hdr[1]
    opcode = b1 & 0x0F
    masked = bool(b2 & 0x80)
    length = b2 & 0x7F
    if length == 126:
        length = struct.unpack("!H", _read_exact(conn, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _read_exact(conn, 8))[0]
    mask = _read_exact(conn, 4) if masked else b""
    data = _read_exact(conn, length)
    if masked:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    if opcode == 0x8:
        return None
    return data.decode("utf-8", errors="replace")


def _read_exact(conn, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("closed")
        buf += chunk
    return buf


class RoastSimulator:
    def __init__(self):
        self._lock = threading.Lock()
        self.state = "IDLE"
        self.profile_id = "medium"
        self.target = 0.0
        self.ramp_mid = 2.0
        self.ramp_k = 1.0
        self.start_temp = 25.0
        self.bean = 25.0
        self.air = 26.0
        self.setpoint = 25.0
        self.heater_pwm = 0
        self.fan_pwm = 0
        self.heater_halted = False
        self.test_spin = False
        self._t0 = 0.0
        self._tick = 0

    def _profile(self):
        return PROFILE_BY_ID.get(self.profile_id, PROFILE_BY_ID["medium"])

    def _elapsed(self) -> float:
        if self._t0 <= 0:
            return 0.0
        return max(0.0, time.time() - self._t0)

    def handle_action(self, action: str, body: dict) -> dict | None:
        with self._lock:
            if action == "START_ROAST":
                p = PROFILE_BY_ID.get(body.get("profile_id", "medium"), PROFILE_BY_ID["medium"])
                self.profile_id = p["id"]
                self.target = p["target_c"]
                self.ramp_mid = p["ramp_midpoint_min"]
                self.ramp_k = p["ramp_steepness"]
                self.start_temp = self.bean
                self.state = "PREHEAT"
                self._t0 = time.time()
                self.test_spin = False
                self.heater_halted = False
                return None
            if action == "STOP_ROAST":
                self.state = "COOLING"
                self.target = 0.0
                return {"type": "roast_action", "action": action, "ok": True}
            if action == "RESUME_ROAST":
                if self.state == "COOLING":
                    self.state = "ROASTING"
                    self._t0 = time.time() - self._elapsed()
                    p = self._profile()
                    self.target = p["target_c"]
                    return {"type": "roast_action", "action": action, "ok": True}
                return {"type": "roast_action", "action": action, "ok": False}
            if action == "FINISH_ROAST":
                self.state = "COOLING"
                self.target = 0.0
                return {"type": "roast_action", "action": action, "ok": True}
            if action == "E_STOP":
                self.state = "IDLE"
                self.target = 0.0
                self.heater_pwm = 0
                self.fan_pwm = 0
                self.test_spin = False
                return None
            if action == "TEST_SPIN":
                if self.state != "IDLE":
                    return {
                        "type": "roast_action",
                        "action": "TEST_SPIN",
                        "ok": False,
                        "test_spin": False,
                        "fan_pwm": self.fan_pwm,
                        "state": self.state,
                    }
                enable = body.get("enable")
                if enable is None:
                    enable = not self.test_spin
                self.test_spin = bool(enable)
                self.fan_pwm = 100 if self.test_spin else 0
                return {
                    "type": "roast_action",
                    "action": "TEST_SPIN",
                    "ok": True,
                    "test_spin": self.test_spin,
                    "fan_pwm": self.fan_pwm,
                    "state": self.state,
                }
            if action == "HEATER_CLEAR_HALT":
                self.heater_halted = False
                return {"type": "heater_status", "heater_halted": False}
            if action == "GET_STATE":
                return {"type": "system_state", "state": self.state}
        return None

    def tick(self) -> None:
        with self._lock:
            self._tick += 1
            noise = random.uniform(-0.15, 0.15)
            elapsed = self._elapsed()

            if self.state in ("PREHEAT", "ROASTING"):
                p = self._profile()
                self.target = p["target_c"]
                self.setpoint = sigmoid_setpoint(
                    self.start_temp,
                    self.target,
                    elapsed,
                    self.ramp_mid,
                    self.ramp_k,
                )
                err = self.setpoint - self.bean
                self.heater_pwm = int(min(100, max(0, 40 + err * 2.5 + random.uniform(-2, 2))))
                self.fan_pwm = 85
                self.bean += err * 0.08 + noise
                self.air = self.bean + random.uniform(6.0, 12.0) + noise
                if self.state == "PREHEAT" and self.bean >= 150:
                    self.state = "ROASTING"
            elif self.state == "COOLING":
                self.setpoint = 0.0
                self.heater_pwm = 0
                self.fan_pwm = 100
                self.bean = max(33.0, self.bean - 0.35 + noise * 0.3)
                self.air = max(32.0, self.air - 0.4 + noise * 0.3)
                if self.bean <= 34.0:
                    self.state = "IDLE"
                    self.fan_pwm = 0
                    self.target = 0.0
            elif self.test_spin:
                self.heater_pwm = 0
                self.fan_pwm = 100
                self.bean += noise * 0.05
                self.air = self.bean + 1.0
            else:
                self.heater_pwm = 0
                if not self.test_spin:
                    self.fan_pwm = 0
                self.setpoint = self.bean
                ambient = 24.0 + math.sin(self._tick * 0.05) * 0.3
                self.bean += (ambient - self.bean) * 0.02 + noise * 0.1
                self.air = self.bean + random.uniform(0.5, 2.0)

    def telemetry(self) -> dict:
        with self._lock:
            return {
                "type": "telemetry",
                "timestamp": round(self._elapsed(), 1),
                "temp": round(self.bean, 1),
                "temp_bean": round(self.bean, 1),
                "temp_air": round(self.air, 1),
                "target": self.target,
                "setpoint": round(self.setpoint, 1),
                "ramp_midpoint_min": self.ramp_mid,
                "ramp_steepness": self.ramp_k,
                "heater_pwm": self.heater_pwm,
                "fan_pwm": self.fan_pwm,
                "state": self.state,
                "heater_halted": self.heater_halted,
                "sensor_fault": None,
                "sensor_fault_bean": None,
                "sensor_fault_air": None,
                "can_resume": self.state == "COOLING",
                "test_spin": self.test_spin,
            }


class BenchSimulator:
    def __init__(self):
        self._lock = threading.Lock()
        self.bean = 28.0
        self.air = 30.0
        self.fan_pwm = 0
        self.heater_pwm = 0
        self.heating = False
        self.target = 100.0
        self.controller = "mpc"
        self.pid_kp, self.pid_ki, self.pid_kd = 1.8, 0.09, 0.0
        self.weight_tracking = 2.0
        self.weight_heater_chg = 0.3
        self.weight_overshoot = 5.0
        self.horizon = 30

    def snapshot(self, msg_type: str = "bench_telemetry") -> dict:
        with self._lock:
            return {
                "type": msg_type,
                "temp": round(self.bean, 1),
                "temp_bean": round(self.bean, 1),
                "temp_air": round(self.air, 1),
                "fan_pwm": self.fan_pwm,
                "heater_pwm": self.heater_pwm,
                "heating": self.heating,
                "target": round(self.target, 1) if self.heating else None,
                "controller": self.controller,
                "pid_kp": self.pid_kp,
                "pid_ki": self.pid_ki,
                "pid_kd": self.pid_kd,
                "weight_tracking": self.weight_tracking,
                "weight_heater_chg": self.weight_heater_chg,
                "weight_overshoot": self.weight_overshoot,
                "horizon": self.horizon,
                "sensor_fault": None,
                "sensor_fault_bean": None,
                "sensor_fault_air": None,
            }

    def handle_action(self, action: str, body: dict) -> dict:
        with self._lock:
            if action == "FAN_SET":
                self.fan_pwm = int(max(0, min(100, float(body.get("percent", 0)))))
            elif action == "FAN_OFF":
                self.fan_pwm = 0
            elif action == "HEAT_START":
                self.heating = True
                self.target = float(body.get("target", 100))
                self._t0 = time.time()
            elif action in ("HEAT_STOP", "E_STOP"):
                self.heating = False
                self.heater_pwm = 0
            elif action == "HEAT_SET_TARGET":
                self.target = float(body.get("target", self.target))
            elif action == "SET_CONTROLLER":
                mode = body.get("mode", "mpc")
                if mode in ("pid", "mpc"):
                    self.controller = mode
            elif action == "PID_SET":
                if "kp" in body:
                    self.pid_kp = float(body["kp"])
                if "ki" in body:
                    self.pid_ki = float(body["ki"])
                if "kd" in body:
                    self.pid_kd = float(body["kd"])
            elif action == "MPC_SET":
                if "weight_tracking" in body:
                    self.weight_tracking = float(body["weight_tracking"])
                if "weight_heater_chg" in body:
                    self.weight_heater_chg = float(body["weight_heater_chg"])
                if "weight_overshoot" in body:
                    self.weight_overshoot = float(body["weight_overshoot"])
                if "horizon" in body:
                    self.horizon = int(body["horizon"])
        snap = self.snapshot()
        return {"type": "bench_ack", "action": action, "ok": True, **snap}

    def tick(self) -> None:
        with self._lock:
            if self.heating:
                err = self.target - self.air
                self.heater_pwm = int(min(100, max(0, 35 + err * 3)))
                self.fan_pwm = max(self.fan_pwm, 40)
                self.air += err * 0.06 + random.uniform(-0.1, 0.1)
                self.bean += (self.air - self.bean) * 0.15 + random.uniform(-0.1, 0.1)
            else:
                self.heater_pwm = 0
                self.bean += (25.5 - self.bean) * 0.03
                self.air += (26.0 - self.air) * 0.03


roast = RoastSimulator()
bench = BenchSimulator()
_ws_clients: list[tuple[object, str]] = []
_ws_lock = threading.Lock()


def _register_ws(conn, path: str) -> None:
    with _ws_lock:
        _ws_clients.append((conn, path))


def _unregister_ws(conn) -> None:
    with _ws_lock:
        _ws_clients[:] = [(c, p) for c, p in _ws_clients if c is not conn]


def _broadcast_loop() -> None:
    while True:
        roast.tick()
        bench.tick()
        t_msg = json.dumps(roast.telemetry())
        b_msg = json.dumps(bench.snapshot())
        with _ws_lock:
            dead = []
            for conn, path in _ws_clients:
                try:
                    if path == "/ws/telemetry":
                        ws_send_text(conn, t_msg)
                    elif path == "/ws/bench":
                        ws_send_text(conn, b_msg)
                except (OSError, ConnectionError):
                    dead.append(conn)
            for conn in dead:
                _unregister_ws(conn)
        time.sleep(TICK_S)


class Handler(BaseHTTPRequestHandler):
    server_version = "MockRoasterUI/1.0"

    def log_message(self, fmt, *args):
        print(f"[mock] {self.address_string()} {fmt % args}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if self.headers.get("Upgrade", "").lower() == "websocket":
            self._handle_websocket(path)
            return
        if path == "/api/profiles":
            body = json.dumps({"profiles": PROFILES}).encode()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/bench/status":
            body = json.dumps(bench.snapshot()).encode()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def _handle_websocket(self, path: str) -> None:
        if path not in ("/ws/telemetry", "/ws/bench"):
            self.send_error(404)
            return
        key = self.headers.get("Sec-WebSocket-Key", "")
        if not key:
            self.send_error(400)
            return
        accept = ws_accept_key(key)
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        conn = self.connection
        _register_ws(conn, path)
        if path == "/ws/bench":
            ready = {
                "type": "bench_ready",
                "defaults": {
                    "pid": {"kp": 1.8, "ki": 0.09, "kd": 0.0},
                    "mpc": {
                        "weight_tracking": 2.0,
                        "weight_heater_chg": 0.3,
                        "weight_overshoot": 5.0,
                        "horizon": 30,
                    },
                },
                **bench.snapshot(),
            }
            ws_send_text(conn, json.dumps(ready))
        try:
            while True:
                raw = ws_recv_text(conn)
                if raw is None:
                    break
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                action = body.get("action", "")
                if path == "/ws/telemetry":
                    reply = roast.handle_action(action, body)
                    if reply:
                        ws_send_text(conn, json.dumps(reply))
                else:
                    reply = bench.handle_action(action, body)
                    ws_send_text(conn, json.dumps(reply))
        finally:
            _unregister_ws(conn)
            try:
                conn.close()
            except OSError:
                pass


def main() -> None:
    random.seed(42)
    threading.Thread(target=_broadcast_loop, daemon=True).start()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Mock roaster UI server on http://{HOST}:{PORT}")
    print("  GET  /api/profiles")
    print("  WS   /ws/telemetry  (dashboard)")
    print("  WS   /ws/bench      (hardware test)")
    print()
    print("Point the frontend at this host (e.g. 127.0.0.1 coffee in hosts, or localhost:8000).")
    print("Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()

"""
Real Raspberry Pi hardware manager for the coffee roaster.

Enable on the Pi:  python api/main.py
"""

import asyncio
import time
from collections import deque

from hardware.heater import RoasterHeater
from hardware.motor import RoasterMotor
from hardware.pid import PIDController
from hardware.roast_logger import RoastDataLogger
from hardware.thermocouple import RoasterThermocouple, read_thermocouple
import config as cfg


class RoasterController:
    def __init__(self):
        self.is_running = False
        self.state = "IDLE"
        self.telemetry_queue = asyncio.Queue()

        self.current_temp = 20.0
        self.target_temp = 0.0
        self.heater_output = 0.0
        self.fan_pwm = 0
        self.start_time = 0.0
        self.profile_id = ""
        self._session_outcome = "completed"

        self.pid = PIDController()
        self._ror_samples = deque(maxlen=cfg.ROR_WINDOW_SAMPLES)
        self._logger = RoastDataLogger(hardware_mode=cfg.HARDWARE_MODE)

        self._tc = RoasterThermocouple()
        self._heater = RoasterHeater()
        self._fan = RoasterMotor()

    async def start(self):
        self.is_running = True
        asyncio.create_task(self._telemetry_loop())
        asyncio.create_task(self._heater_loop())

    def shutdown(self):
        self.is_running = False
        self._heater.stop()
        self._fan.stop()
        if self._logger.is_active:
            self._logger.end_session("shutdown", self.current_temp)

    def start_roast(self, profile_id="default"):
        if self._logger.is_active:
            self._logger.end_session("replaced", self.current_temp)

        self.profile_id = profile_id
        self._session_outcome = "completed"
        self.target_temp = cfg.target_for_profile(profile_id)
        self.state = "PREHEAT"
        self.start_time = time.time()
        self.pid.reset()
        self._ror_samples.clear()
        self._logger.start_session(profile_id, self.target_temp)
        self._heater.clear_halt()
        self.fan_pwm = self._fan.set_speed()

    def stop_roast(self):
        self._session_outcome = "stopped"
        self.state = "COOLING"
        self.target_temp = 0.0
        self._heater.stop()
        self.fan_pwm = self._fan.set_speed()

    def emergency_stop(self):
        self.state = "IDLE"
        self.target_temp = 0.0
        self._heater.stop()
        self.fan_pwm = self._fan.set_speed(1.0)
        self.pid.reset()
        if self._logger.is_active:
            elapsed = round(time.time() - self.start_time, 1) if self.start_time else 0.0
            self._log_sample(elapsed, self._ror(), event="state:->IDLE:e_stop")
            self._logger.end_session("e_stop", self.current_temp)

    def clear_heater_halt(self):
        self._heater.clear_halt()

    def _ror(self):
        if len(self._ror_samples) < 2:
            return 0.0
        t0, temp0 = self._ror_samples[0]
        t1, temp1 = self._ror_samples[-1]
        dt = t1 - t0
        if dt <= 0:
            return 0.0
        return ((temp1 - temp0) / dt) * 60.0

    def _log_sample(self, elapsed, ror, event=""):
        if not self._logger.is_active:
            return
        self._logger.log_sample(
            elapsed_s=elapsed,
            temp_c=self.current_temp,
            target_c=self.target_temp,
            heater_pwm=self.heater_output,
            fan_pwm=int(self.fan_pwm),
            ror_c_per_min=ror,
            state=self.state,
            event=event,
        )

    async def _telemetry_loop(self):
        while self.is_running:
            temp, _fault = read_thermocouple(self._tc)

            if temp is None:
                await asyncio.sleep(cfg.TELEMETRY_INTERVAL_S)
                continue

            self.current_temp = temp
            self._ror_samples.append((time.time(), temp))

            if temp > cfg.MAX_SAFE_TEMP_C and self.state not in ("IDLE", "ERROR"):
                self._heater.stop()
                prev_state = self.state
                self.state = "ERROR"
                if self._logger.is_active:
                    self._log_sample(
                        round(time.time() - self.start_time, 1) if self.start_time else 0,
                        self._ror(),
                        event=f"overtemp:{prev_state}->ERROR",
                    )
                    self._logger.end_session("error", temp)
                await self.telemetry_queue.put(
                    {
                        "type": "error",
                        "msg": (
                            f"Over-temp shutdown "
                            f"({temp:.1f}°C > {cfg.MAX_SAFE_TEMP_C}°C)"
                        ),
                    }
                )

            prev_state = self.state
            if self.state == "PREHEAT" and temp >= cfg.PREHEAT_THRESHOLD_C:
                self.state = "ROASTING"
            elif self.state == "COOLING" and temp <= cfg.COOL_DOWN_TEMP_C:
                self.state = "IDLE"
                self._fan.stop()
                self.fan_pwm = 0
                if self._logger.is_active:
                    elapsed = (
                        round(time.time() - self.start_time, 1)
                        if self.start_time
                        else 0.0
                    )
                    self._log_sample(
                        elapsed, self._ror(), event="state:COOLING->IDLE"
                    )
                    self._logger.end_session(self._session_outcome, temp)

            ror = self._ror()
            elapsed = (
                round(time.time() - self.start_time, 1) if self.start_time else 0.0
            )

            if self._logger.is_active and self.state in (
                "PREHEAT",
                "ROASTING",
                "COOLING",
            ):
                event = ""
                if prev_state != self.state:
                    event = f"state:{prev_state}->{self.state}"
                self._log_sample(elapsed, ror, event)

            payload = {
                "type": "telemetry",
                "timestamp": elapsed,
                "temp": round(temp, 1),
                "target": self.target_temp,
                "ror": round(ror, 1) if self.state != "IDLE" else 0.0,
                "heater_pwm": round(self.heater_output),
                "fan_pwm": self.fan_pwm,
                "state": self.state,
                "heater_halted": self._heater.halted,
            }
            if self._logger.is_active:
                payload["roast_id"] = self._logger.roast_id
            await self.telemetry_queue.put(payload)
            await asyncio.sleep(cfg.TELEMETRY_INTERVAL_S)

    async def _heater_loop(self):
        while self.is_running:
            if self.state in ("PREHEAT", "ROASTING"):
                output = self.pid.calculate(self.target_temp, self.current_temp)

                if self.current_temp > self.target_temp + cfg.OVERSHOOT_CUTOFF_C:
                    output = 0.0

                self.heater_output = await self._heater.apply_output(output)
            else:
                self._heater.stop()
                self.heater_output = 0.0
                await asyncio.sleep(cfg.TELEMETRY_INTERVAL_S)

"""
Real Raspberry Pi hardware manager for the coffee roaster.

Enable on the Pi:  python api/main.py
"""

import asyncio
import time
from collections import deque

from hardware.heater import RoasterHeater
from hardware.motor import RoasterMotor
from hardware.heater_control import create_heater_controller
from hardware.roast_logger import RoastDataLogger
from hardware.roast_ramp import effective_setpoint
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
        self._roast_start_temp = 20.0
        self._ramp_midpoint_min = cfg.DEFAULT_RAMP_MIDPOINT_MIN
        self._ramp_steepness = cfg.DEFAULT_RAMP_STEEPNESS
        self.effective_target = 0.0
        self._sensor_fault = None
        self._session_outcome = "completed"
        self._test_spin_active = False

        self.heater_controller = create_heater_controller()
        self._ror_samples = deque(maxlen=cfg.ROR_WINDOW_SAMPLES)
        self._logger = RoastDataLogger(hardware_mode=cfg.HARDWARE_MODE)

        self._thermocouple = RoasterThermocouple()
        self._heater = RoasterHeater()
        self._heater.halt()
        self._fan = RoasterMotor()

    def _read_sensors(self):
        temp, fault = read_thermocouple(self._thermocouple)
        if temp is not None:
            self.current_temp = temp
        self._sensor_fault = fault
        return temp, fault

    def _telemetry_payload(self, **extra):
        payload = {
            "type": "telemetry",
            "timestamp": round(self._elapsed_s(), 1),
            "temp": round(self.current_temp, 1) if self._sensor_fault is None else None,
            "target": self.target_temp,
            "setpoint": round(self.effective_target, 1),
            "ramp_midpoint_min": self._ramp_midpoint_min,
            "ramp_steepness": self._ramp_steepness,
            "ror": 0.0,
            "heater_pwm": round(self.heater_output),
            "fan_pwm": self.fan_pwm,
            "state": self.state,
            "heater_halted": self._heater.halted,
            "sensor_fault": self._sensor_fault,
            "can_resume": self.state == "COOLING" and self._logger.is_active,
            "test_spin": self._test_spin_active,
        }
        if self._logger.is_active:
            payload["roast_id"] = self._logger.roast_id
        payload.update(extra)
        return payload

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

    def _elapsed_s(self):
        if not self.start_time:
            return 0.0
        return max(0.0, time.time() - self.start_time)

    def _update_effective_target(self):
        if self.state not in ("PREHEAT", "ROASTING"):
            self.effective_target = self.target_temp
            return self.effective_target
        self.effective_target = effective_setpoint(
            self._roast_start_temp,
            self.target_temp,
            self._elapsed_s(),
            self._ramp_midpoint_min,
            self._ramp_steepness,
        )
        return self.effective_target

    def _push_status_now(self):
        ror = self._ror() if self.state not in ("IDLE",) else 0.0
        self._update_effective_target()
        payload = self._telemetry_payload(ror=round(ror, 1))
        try:
            self.telemetry_queue.put_nowait(payload)
        except Exception:
            pass

    def start_test_spin(self):
        if self.state != "IDLE":
            return False
        self._test_spin_active = True
        self.fan_pwm = self._fan.set_speed()
        self._push_status_now()
        return True

    def stop_test_spin(self):
        if self.state != "IDLE":
            return False
        if not self._test_spin_active:
            return False
        self._test_spin_active = False
        self._fan.stop()
        self.fan_pwm = 0
        self._push_status_now()
        return True

    def start_roast(self, profile_id="default"):
        if self._logger.is_active:
            self._logger.end_session("replaced", self.current_temp)

        self._read_sensors()
        self._test_spin_active = False
        self.profile_id = profile_id
        self._session_outcome = "completed"
        self.target_temp = cfg.target_for_profile(profile_id)
        ramp = cfg.ramp_sigmoid_for_profile(profile_id)
        self._ramp_midpoint_min = ramp["midpoint_min"]
        self._ramp_steepness = ramp["steepness"]
        self._roast_start_temp = self.current_temp
        self.effective_target = self._roast_start_temp
        self.state = "PREHEAT"
        self.start_time = time.time()
        self.heater_controller.reset()
        self._ror_samples.clear()
        self._logger.start_session(profile_id, self.target_temp)
        self._heater.clear_halt()
        self.fan_pwm = self._fan.set_speed()

    def stop_roast(self):
        self._test_spin_active = False
        self._session_outcome = "stopped"
        self.state = "COOLING"
        self.target_temp = 0.0
        self._heater.stop()
        self.fan_pwm = self._fan.set_speed()

    def resume_roast(self):
        if self.state != "COOLING" or not self._logger.is_active:
            return False
        self.target_temp = cfg.target_for_profile(self.profile_id)
        if self.current_temp >= cfg.PREHEAT_THRESHOLD_C:
            self.state = "ROASTING"
        else:
            self.state = "PREHEAT"
        self._heater.clear_halt()
        self.fan_pwm = self._fan.set_speed()
        return True

    def finish_roast(self):
        if not self._logger.is_active:
            return False
        elapsed = round(time.time() - self.start_time, 1) if self.start_time else 0.0
        self._log_sample(elapsed, self._ror(), event="finish_now")
        self._logger.end_session("finished", self.current_temp)
        if self.current_temp <= cfg.COOL_DOWN_TEMP_C:
            self.state = "IDLE"
            self._fan.stop()
            self.fan_pwm = 0
            self._heater.clear_halt()
        return True

    def emergency_stop(self):
        self._test_spin_active = False
        self.state = "IDLE"
        self.target_temp = 0.0
        self._heater.stop()
        self.fan_pwm = self._fan.set_speed()
        self.heater_controller.reset()
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
            target_c=self.effective_target,
            heater_pwm=self.heater_output,
            fan_pwm=int(self.fan_pwm),
            ror_c_per_min=ror,
            state=self.state,
            event=event,
        )

    async def _telemetry_loop(self):
        while self.is_running:
            self._read_sensors()
            self._update_effective_target()

            if self._sensor_fault is None:
                self._ror_samples.append((time.time(), self.current_temp))

            if (
                self._sensor_fault is None
                and self.current_temp > cfg.MAX_SAFE_TEMP_C
                and self.state not in ("IDLE", "ERROR")
            ):
                self._heater.stop()
                prev_state = self.state
                self.state = "ERROR"
                if self._logger.is_active:
                    self._log_sample(
                        round(self._elapsed_s(), 1),
                        self._ror(),
                        event=f"overtemp:{prev_state}->ERROR",
                    )
                    self._logger.end_session("error", self.current_temp)
                await self.telemetry_queue.put(
                    {
                        "type": "error",
                        "msg": (
                            f"Over-temp shutdown "
                            f"({self.current_temp:.1f}°C > {cfg.MAX_SAFE_TEMP_C}°C)"
                        ),
                    }
                )

            prev_state = self.state
            if self._sensor_fault is None:
                if self.state == "PREHEAT" and self.current_temp >= cfg.PREHEAT_THRESHOLD_C:
                    self.state = "ROASTING"
                elif self.state == "COOLING" and self.current_temp <= cfg.COOL_DOWN_TEMP_C:
                    self.state = "IDLE"
                    self._test_spin_active = False
                    self._fan.stop()
                    self.fan_pwm = 0
                    self._heater.clear_halt()
                    if self._logger.is_active:
                        self._log_sample(
                            round(self._elapsed_s(), 1),
                            self._ror(),
                            event="state:COOLING->IDLE",
                        )
                        self._logger.end_session(self._session_outcome, self.current_temp)

            ror = self._ror() if self._sensor_fault is None else 0.0

            if self._logger.is_active and self.state in (
                "PREHEAT",
                "ROASTING",
                "COOLING",
            ):
                event = ""
                if prev_state != self.state:
                    event = f"state:{prev_state}->{self.state}"
                self._log_sample(round(self._elapsed_s(), 1), ror, event)

            await self.telemetry_queue.put(
                self._telemetry_payload(
                    ror=round(ror, 1) if self.state != "IDLE" else 0.0,
                )
            )
            await asyncio.sleep(cfg.TELEMETRY_INTERVAL_S)

    async def _heater_loop(self):
        while self.is_running:
            if self.state in ("PREHEAT", "ROASTING"):
                self._read_sensors()
                setpoint = self._update_effective_target()

                if self._sensor_fault is None:
                    output = self.heater_controller.calculate(
                        setpoint, self.current_temp
                    )
                    if self.current_temp > self.target_temp + cfg.OVERSHOOT_CUTOFF_C:
                        output = 0.0
                    self.heater_output = await self._heater.apply_output(output)
                else:
                    self.heater_output = await self._heater.apply_output(
                        self.heater_output
                    )
            else:
                self._heater.off()
                self.heater_output = 0.0
                await asyncio.sleep(cfg.TELEMETRY_INTERVAL_S)

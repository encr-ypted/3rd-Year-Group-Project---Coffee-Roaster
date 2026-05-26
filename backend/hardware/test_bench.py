"""
Standalone hardware bench for first power-on and wiring checks.

Run via:  python api/hardware_test.py  (port 8001)

Does not use RoasterController — owns GPIO directly so it cannot
fight the roast PID loop. Do not run both servers on the Pi at once.
"""

import asyncio

import config as cfg
from hardware.heater import RoasterHeater
from hardware.motor import RoasterMotor
from hardware.pid import PIDController
from hardware.thermocouple import RoasterThermocouple, read_thermocouple


class HardwareTestBench:
    def __init__(self):
        self.is_running = False
        self.session_active = False
        self.message_queue: asyncio.Queue = asyncio.Queue()

        self.temp_c = None
        self.sensor_fault: str | None = None
        self.heater_pwm = 0
        self.fan_pwm = 0

        self._tc = RoasterThermocouple()
        self._heater = RoasterHeater()
        self._fan = RoasterMotor()
        self._pid_task: asyncio.Task | None = None
        self._pid_active = False
        self._full_power_ramp = False
        self.pid_target = 0.0
        self.pid = PIDController()

    async def start(self) -> None:
        self.is_running = True
        asyncio.create_task(self._telemetry_loop())

    def shutdown(self) -> None:
        self.is_running = False
        self.session_active = False
        self.stop_heating()
        self._fan.stop()
        self.fan_pwm = 0

    def start_session(self) -> None:
        self.session_active = True
        self.stop_heating()
        self._fan.stop()
        self.fan_pwm = 0

    def stop_session(self) -> None:
        self.session_active = False
        self.stop_heating()
        self._fan.stop()
        self.fan_pwm = 0

    def emergency_stop(self) -> None:
        self.stop_session()

    def read_sensors(self) -> dict:
        temp, fault = read_thermocouple(self._tc)
        self.temp_c = temp
        self.sensor_fault = fault
        return {
            "temp_c": self.temp_c,
            "sensor_fault": fault,
            "heater_pwm": self.heater_pwm,
            "fan_pwm": self.fan_pwm,
            "session_active": self.session_active,
        }

    def _heater_mode(self) -> str:
        if not self._pid_active:
            return "off"
        if self._full_power_ramp:
            return "ramp"
        return "pid"

    def _clamp_target(self, target: float) -> float:
        return max(20.0, min(float(target), cfg.MAX_SAFE_TEMP_C - 5.0))

    def pid_gains(self) -> dict:
        return self.pid.as_dict()

    def set_pid_gains(
        self,
        kp: float | None = None,
        ki: float | None = None,
        kd: float | None = None,
        *,
        reset: bool = False,
    ) -> dict:
        return self.pid.set_gains(kp, ki, kd, reset=reset)

    def telemetry_payload(self) -> dict:
        gains = self.pid_gains()
        return {
            "type": "bench_telemetry",
            "temp": round(self.temp_c, 1) if self.temp_c is not None else None,
            "sensor_fault": self.sensor_fault,
            "heater_pwm": self.heater_pwm,
            "heater_mode": self._heater_mode(),
            "pid_active": self._pid_active,
            "pid_target": (
                round(self.pid_target, 1) if self.pid_target > 0 else None
            ),
            "pid_kp": gains["kp"],
            "pid_ki": gains["ki"],
            "pid_kd": gains["kd"],
            "fan_pwm": self.fan_pwm,
            "session_active": self.session_active,
        }

    def set_fan(self, percent: float) -> int:
        speed = max(0.0, min(100.0, percent)) / 100.0
        if speed <= 0:
            self._fan.stop()
            self.fan_pwm = 0
            return 0
        self.fan_pwm = self._fan.set_speed(speed)
        return self.fan_pwm

    def stop_fan(self) -> None:
        self._fan.stop()
        self.fan_pwm = 0

    def heat_to_target(self, target_temp: float) -> float:
        """Full power until near target, then PID holds setpoint."""
        self.session_active = True
        self.stop_heating()

        self.pid_target = self._clamp_target(target_temp)
        self.pid.reset()
        self._pid_active = True
        self._full_power_ramp = True
        self._pid_task = asyncio.create_task(self._run_heat_loop())
        return self.pid_target

    def set_target(self, target_temp: float) -> float:
        self.pid_target = self._clamp_target(target_temp)
        return self.pid_target

    def stop_heating(self) -> None:
        self._pid_active = False
        self._full_power_ramp = False
        task = self._pid_task
        self._pid_task = None
        if task and not task.done():
            task.cancel()
        self._heater.stop()
        self.heater_pwm = 0

    def _pid_output(self, temp: float) -> float:
        if temp > self.pid_target + cfg.OVERSHOOT_CUTOFF_C:
            return 0.0
        if temp < self.pid_target - cfg.BENCH_FULL_POWER_BAND_C:
            return 100.0
        return self.pid.calculate(self.pid_target, temp)

    async def _run_heat_loop(self) -> None:
        my_task = asyncio.current_task()
        try:
            while self._pid_active and self.is_running and self.session_active:
                temp, fault = read_thermocouple(self._tc)
                self.temp_c = temp
                self.sensor_fault = fault

                if temp is None:
                    self._pid_active = False
                    await self.message_queue.put(
                        {
                            "type": "error",
                            "msg": f"Heating stopped — thermocouple fault: {fault}",
                        }
                    )
                    break

                if temp > cfg.MAX_SAFE_TEMP_C:
                    self._pid_active = False
                    await self.message_queue.put(
                        {
                            "type": "error",
                            "msg": (
                                f"Heating stopped — over-temp ({temp:.1f}°C)"
                            ),
                        }
                    )
                    break

                band = cfg.BENCH_FULL_POWER_BAND_C
                if temp < self.pid_target - band:
                    self._full_power_ramp = True
                    self._heater.force_on()
                    self.heater_pwm = 100
                    await asyncio.sleep(cfg.TELEMETRY_INTERVAL_S)
                    continue

                if self._full_power_ramp:
                    self._full_power_ramp = False
                    self._heater.stop()
                    self.pid.reset()

                output = self._pid_output(temp)
                self.heater_pwm = round(
                    await self._heater.apply_output(output), 1
                )
        except asyncio.CancelledError:
            raise
        finally:
            if self._pid_task is not my_task:
                return
            self._pid_task = None
            if not self._pid_active:
                return
            self._pid_active = False
            self._full_power_ramp = False
            self._heater.stop()
            self.heater_pwm = 0

    async def _telemetry_loop(self) -> None:
        while self.is_running:
            try:
                sensors = self.read_sensors()
                fault = sensors.get("sensor_fault")

                if sensors["temp_c"] is None:
                    if self._pid_active:
                        self.stop_heating()
                    self._fan.stop()
                    self.fan_pwm = 0
                    await self.message_queue.put(self.telemetry_payload())
                    if fault:
                        await self.message_queue.put(
                            {
                                "type": "error",
                                "msg": f"Thermocouple: {fault} — outputs off",
                            }
                        )
                    await asyncio.sleep(cfg.TELEMETRY_INTERVAL_S)
                    continue

                if (
                    sensors["temp_c"] > cfg.MAX_SAFE_TEMP_C
                    and self.session_active
                ):
                    self.emergency_stop()
                    await self.message_queue.put(
                        {
                            "type": "error",
                            "msg": (
                                f"Over-temp ({sensors['temp_c']:.1f}°C) — "
                                "session stopped"
                            ),
                        }
                    )

                await self.message_queue.put(self.telemetry_payload())
                await asyncio.sleep(cfg.TELEMETRY_INTERVAL_S)
            except Exception as exc:
                await self.message_queue.put(
                    {"type": "error", "msg": f"Telemetry error: {exc}"}
                )
                await asyncio.sleep(1)

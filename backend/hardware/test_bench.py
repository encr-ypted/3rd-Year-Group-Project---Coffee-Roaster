"""
Standalone hardware bench for first power-on and wiring checks.

Run via:  python api/hardware_test.py  (port 8001)

Does not use RoasterController — owns GPIO directly so it cannot
fight the roast PID loop. Do not run both servers on the Pi at once.
"""

import asyncio
import time

import config as cfg
from hardware.heater import RoasterHeater
from hardware.motor import RoasterMotor
from hardware.thermocouple import RoasterThermocouple


class HardwareTestBench:
    def __init__(self):
        self.is_running = False
        self.session_active = False
        self.message_queue: asyncio.Queue = asyncio.Queue()

        self.temp_c = None
        self.temp_raw_c = None
        self.heater_pwm = 0
        self.fan_pwm = 0

        self._tc = RoasterThermocouple()
        self._heater = RoasterHeater()
        self._fan = RoasterMotor()
        self._heater_task: asyncio.Task | None = None

    async def start(self) -> None:
        self.is_running = True
        asyncio.create_task(self._telemetry_loop())

    def shutdown(self) -> None:
        self.is_running = False
        self.session_active = False
        self._cancel_heater_task()
        self._heater.stop()
        self._fan.stop()
        self.heater_pwm = 0
        self.fan_pwm = 0

    def start_session(self) -> None:
        self.session_active = True
        self._cancel_heater_task()
        self._heater.stop()
        self._fan.stop()
        self.heater_pwm = 0
        self.fan_pwm = 0

    def stop_session(self) -> None:
        self.session_active = False
        self._cancel_heater_task()
        self._heater.stop()
        self._fan.stop()
        self.heater_pwm = 0
        self.fan_pwm = 0

    def emergency_stop(self) -> None:
        self.stop_session()

    def read_sensors(self) -> dict:
        self.temp_raw_c = self._tc.read_raw_temperature()
        self.temp_c = self._tc.read_filtered_temperature()
        return {
            "temp_raw_c": self.temp_raw_c,
            "temp_c": self.temp_c,
            "heater_pwm": self.heater_pwm,
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

    def heater_on(self) -> None:
        self._cancel_heater_task()
        self._heater.force_on()
        self.heater_pwm = 100

    def heater_off(self) -> None:
        self._cancel_heater_task()
        self._heater.stop()
        self.heater_pwm = 0

    def heater_pulse(self, percent: float) -> None:
        self._cancel_heater_task()
        percent = max(0.0, min(100.0, percent))
        if percent <= 0:
            self.heater_off()
            return
        self._heater_task = asyncio.create_task(self._run_heater_pulse(percent))

    def _cancel_heater_task(self) -> None:
        if self._heater_task and not self._heater_task.done():
            self._heater_task.cancel()
        self._heater_task = None

    async def _run_heater_pulse(self, percent: float) -> None:
        try:
            self.heater_pwm = round(await self._heater.apply_output(percent), 1)
        except asyncio.CancelledError:
            self._heater.stop()
            self.heater_pwm = 0
            raise

    async def _telemetry_loop(self) -> None:
        while self.is_running:
            sensors = self.read_sensors()

            if sensors["temp_c"] is None:
                self._heater.stop()
                self._fan.stop()
                self.heater_pwm = 0
                self.fan_pwm = 0
                await self.message_queue.put(
                    {
                        "type": "error",
                        "msg": "Thermocouple fault — outputs off",
                    }
                )
                await asyncio.sleep(1)
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

            await self.message_queue.put(
                {
                    "type": "bench_telemetry",
                    "temp": round(sensors["temp_c"], 1),
                    "temp_raw": sensors["temp_raw_c"],
                    "heater_pwm": self.heater_pwm,
                    "fan_pwm": self.fan_pwm,
                    "session_active": self.session_active,
                }
            )
            await asyncio.sleep(cfg.TELEMETRY_INTERVAL_S)

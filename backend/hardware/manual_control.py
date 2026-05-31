"""
Verified hardware bench — GPIO wiring and PID checks.

Run:  python api/hardware_test.py   (port 8001)
Do not run api/main.py at the same time.
"""

import asyncio

import config as cfg
from hardware.heater import RoasterHeater
from hardware.motor import RoasterMotor
from hardware.pid import PIDController
from hardware.thermocouple import RoasterThermocouple, read_thermocouple


class HardwareTestBench:
    def __init__(self):
        self.running = False
        self.telemetry_queue = asyncio.Queue()

        self.temp_c = None
        self._last_good_temp = None
        self.fan_pwm = 0
        self.heater_pwm = 0

        self.heating = False
        self.target_c = 0.0
        self.pid = PIDController()

        self._thermocouple = RoasterThermocouple()
        self._heater = RoasterHeater()
        self._fan = RoasterMotor()
        self._heat_task = None

    async def run(self):
        self.running = True
        self.fan_pwm = self._fan.set_speed(cfg.FAN_DEFAULT_SPEED)
        asyncio.create_task(self._telemetry_loop())

    def close(self):
        self.running = False
        self.stop_heat()
        self._fan.stop()
        self.fan_pwm = 0

    def set_pid(self, kp, ki, kd, reset=False):
        return self.pid.set_gains(kp, ki, kd, reset=reset)

    def set_fan(self, percent):
        pct = max(0.0, min(100.0, percent))
        if pct <= 0:
            self._fan.stop()
            self.fan_pwm = 0
            return 0
        self.fan_pwm = self._fan.set_speed(pct / 100.0)
        return self.fan_pwm

    def fan_off(self):
        self._fan.stop()
        self.fan_pwm = 0

    def start_heat(self, target_c):
        self.stop_heat()
        self._heater.clear_halt()
        self.target_c = max(20.0, min(float(target_c), cfg.MAX_SAFE_TEMP_C - 5.0))
        self.pid.reset()
        self.heating = True
        self._heat_task = asyncio.create_task(self._heat_loop())
        return self.target_c

    def set_target(self, target_c):
        self.target_c = max(20.0, min(float(target_c), cfg.MAX_SAFE_TEMP_C - 5.0))
        return self.target_c

    def stop_heat(self):
        self.heating = False
        task = self._heat_task
        self._heat_task = None
        if task and not task.done():
            task.cancel()
        self._heater.halt()
        self.heater_pwm = 0

    def _heater_duty(self, temp):
        if temp > self.target_c + cfg.OVERSHOOT_CUTOFF_C:
            return 0.0
        return self.pid.calculate(self.target_c, temp)

    async def _heat_loop(self):
        owner = asyncio.current_task()
        try:
            while self.heating and self.running:
                self._poll_temp()
                temp = self._last_good_temp
                if temp is None:
                    await asyncio.sleep(cfg.TELEMETRY_INTERVAL_S)
                    continue

                if temp > cfg.MAX_SAFE_TEMP_C:
                    self.heating = False
                    break

                duty = self._heater_duty(temp)
                self.heater_pwm = round(await self._heater.apply_output(duty), 1)
                if self._heater.halted:
                    await asyncio.sleep(cfg.TELEMETRY_INTERVAL_S)
        except asyncio.CancelledError:
            raise
        finally:
            if self._heat_task is owner:
                self._heat_task = None
            self._heater.halt()
            self.heater_pwm = 0
            self.heating = False

    def snapshot(self):
        pid_config = self.pid.get_pid_config()

        return {
            "type": "bench_telemetry",
            "temp": round(self.temp_c, 1) if self.temp_c is not None else None,
            "fan_pwm": self.fan_pwm,
            "heater_pwm": self.heater_pwm,
            "heating": self.heating,
            "target": round(self.target_c, 1) if self.heating else None,
            "pid_kp": pid_config["kp"],
            "pid_ki": pid_config["ki"],
            "pid_kd": pid_config["kd"],
        }

    def _poll_temp(self):
        try:
            temp, _fault = read_thermocouple(self._thermocouple)
            self.temp_c = temp
            if temp is not None:
                self._last_good_temp = temp
        except Exception:
            self.temp_c = None

    async def _telemetry_loop(self):
        while self.running:
            try:
                self._poll_temp()
                await self.telemetry_queue.put(self.snapshot())
            except Exception:
                pass
            await asyncio.sleep(cfg.TELEMETRY_INTERVAL_S)

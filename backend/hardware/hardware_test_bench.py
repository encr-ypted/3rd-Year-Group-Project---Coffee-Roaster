"""Hardware bench — GPIO wiring and heater control checks (used by api/hardware_test.py)."""

import asyncio

import config as cfg
from hardware.control.heater_control import create_heater_controller
from hardware.devices.heater import RoasterHeater
from hardware.devices.motor import RoasterMotor
from hardware.devices.thermocouple import RoasterThermocouple, read_thermocouple


class HardwareTestBench:
    def __init__(self):
        self.running = False
        self.telemetry_queue = asyncio.Queue()

        self.temp_c = None
        self.sensor_fault = None
        self._last_good_temp = None
        self.fan_pwm = 0
        self.heater_pwm = 0

        self.heating = False
        self.target_c = 0.0
        self.controller_mode = getattr(
            cfg, "BENCH_DEFAULT_CONTROLLER", cfg.HEATER_CONTROLLER
        ).lower()
        self.heater_controller = create_heater_controller(self.controller_mode)

        self._thermocouple = RoasterThermocouple()
        self._heater = RoasterHeater()
        self._heater.halt()
        self._fan = RoasterMotor()
        self._heat_task = None

    async def run(self):
        self.running = True
        self.fan_pwm = self._fan.set_speed()
        asyncio.create_task(self._telemetry_loop())

    def close(self):
        self.running = False
        self.stop_heat()
        self._fan.stop()
        self.fan_pwm = 0

    def set_pid(self, kp, ki, kd, reset=False):
        ctrl = self.heater_controller
        if hasattr(ctrl, "set_gains"):
            return ctrl.set_gains(kp, ki, kd, reset=reset)
        return ctrl.get_pid_config()

    def set_mpc(
        self,
        weight_tracking=None,
        weight_heater_chg=None,
        weight_overshoot=None,
        horizon=None,
        reset=False,
    ):
        ctrl = self.heater_controller
        if hasattr(ctrl, "set_params"):
            return ctrl.set_params(
                weight_tracking=weight_tracking,
                weight_heater_chg=weight_heater_chg,
                weight_overshoot=weight_overshoot,
                horizon=horizon,
                reset=reset,
            )
        return ctrl.get_mpc_config()

    def set_controller(self, mode):
        mode = (mode or "").lower()
        if mode not in ("pid", "mpc"):
            return False
        if self.heating:
            self.stop_heat()
        self.controller_mode = mode
        self.heater_controller = create_heater_controller(mode)
        return True

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
        self.heater_controller.reset()
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
        if self.temp_c is not None and self.temp_c > self.target_c + cfg.OVERSHOOT_CUTOFF_C:
            return 0.0
        return self.heater_controller.calculate(self.target_c, temp)

    async def _heat_loop(self):
        owner = asyncio.current_task()
        try:
            while self.heating and self.running:
                self._poll_temp()
                temp = self._last_good_temp
                if temp is None:
                    self.heater_pwm = round(
                        await self._heater.apply_output(self.heater_pwm), 1
                    )
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
        payload = {
            "type": "bench_telemetry",
            "temp": round(self.temp_c, 1) if self.temp_c is not None else None,
            "sensor_fault": self.sensor_fault,
            "fan_pwm": self.fan_pwm,
            "heater_pwm": self.heater_pwm,
            "heating": self.heating,
            "target": round(self.target_c, 1) if self.heating else None,
            "controller": self.controller_mode,
        }
        ctrl = self.heater_controller
        if self.controller_mode == "mpc":
            payload.update(ctrl.get_mpc_config())
        else:
            g = ctrl.get_pid_config()
            payload["pid_kp"] = g["kp"]
            payload["pid_ki"] = g["ki"]
            payload["pid_kd"] = g["kd"]
        return payload

    def _poll_temp(self):
        try:
            temp, fault = read_thermocouple(self._thermocouple)
            self.sensor_fault = fault
            if temp is not None:
                self.temp_c = temp
                self._last_good_temp = temp
        except Exception as exc:
            self.sensor_fault = str(exc)
            self.temp_c = None

    async def _telemetry_loop(self):
        while self.running:
            try:
                self._poll_temp()
                await self.telemetry_queue.put(self.snapshot())
            except Exception:
                pass
            await asyncio.sleep(cfg.TELEMETRY_INTERVAL_S)

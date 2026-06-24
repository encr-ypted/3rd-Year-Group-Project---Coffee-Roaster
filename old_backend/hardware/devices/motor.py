import threading
import time

from gpiozero import PWMOutputDevice

from config import (
    FAN_DEFAULT_SPEED,
    FAN_PWM_FREQUENCY_HZ,
    FAN_PWM_GPIO,
    FAN_RAMP_STEP_DELAY_S,
    FAN_RAMP_STEPS,
)


class RoasterMotor:
    def __init__(
        self,
        pwm_pin=FAN_PWM_GPIO,
        pwm_frequency=FAN_PWM_FREQUENCY_HZ,
    ):
        self._pwm = PWMOutputDevice(
            pwm_pin,
            frequency=pwm_frequency,
            active_high=False,
            initial_value=0.0,
        )
        self._speed = 0.0
        self._default_speed = FAN_DEFAULT_SPEED
        self._lock = threading.Lock()
        self._ramp_abort = threading.Event()

    def _apply_pwm(self, speed):
        self._pwm.value = speed
        self._speed = speed

    def _ramp_worker(self, target):
        with self._lock:
            start = self._speed
            steps = FAN_RAMP_STEPS
            delay = FAN_RAMP_STEP_DELAY_S
        for step in range(1, steps + 1):
            if self._ramp_abort.is_set():
                return
            level = start + (target - start) * (step / steps)
            with self._lock:
                self._apply_pwm(level)
            if step < steps:
                time.sleep(delay)

    def set_speed(self, speed=None, ramp=True):
        if speed is None:
            speed = self._default_speed
        speed = max(0.0, min(1.0, speed))

        try:
            self._ramp_abort.set()
            with self._lock:
                if speed <= self._speed or not ramp or FAN_RAMP_STEPS <= 0:
                    self._apply_pwm(speed)
                    return int(self._speed * 100)

                self._ramp_abort.clear()
                threading.Thread(
                    target=self._ramp_worker,
                    args=(speed,),
                    daemon=True,
                ).start()
                return int(speed * 100)
        except Exception:
            self.stop()
            return 0

    def stop(self):
        self._ramp_abort.set()
        with self._lock:
            self._apply_pwm(0.0)

    def read_speed(self):
        return self._speed

    def read_speed_percent(self):
        return int(self._speed * 100)

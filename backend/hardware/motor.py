from gpiozero import PWMOutputDevice

from config import FAN_DEFAULT_SPEED, FAN_PWM_FREQUENCY_HZ, FAN_PWM_GPIO


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

    def set_speed(self, speed=None):
        if speed is None:
            speed = self._default_speed
        speed = max(0.0, min(1.0, speed))
        try:
            self._pwm.value = speed
            self._speed = speed
            return int(speed * 100)
        except Exception:
            self.stop()
            return 0

    def stop(self):
        self._pwm.value = 0.0
        self._speed = 0.0

    def read_speed(self):
        return self._speed

    def read_speed_percent(self):
        return int(self._speed * 100)

"""L298N fan motor driver with PWM speed control."""

from gpiozero import Motor, PWMOutputDevice


class RoasterMotor:
    """Cooling fan via L298N (IN1/IN2 direction, ENA PWM)."""

    def __init__(self, in1=23, in2=24, ena=12, pwm_frequency=1000):
        self._motor = Motor(forward=in1, backward=in2)
        self._enable = PWMOutputDevice(ena, frequency=pwm_frequency)
        self._speed = 0.0

    def set_speed(self, speed=1.0):
        speed = max(0.0, min(1.0, speed))
        try:
            self._enable.value = speed
            self._motor.forward()
            self._speed = speed
            return int(speed * 100)
        except Exception:
            self.stop()
            return 0

    def stop(self):
        self._motor.stop()
        self._enable.value = 0
        self._speed = 0.0

    def read_speed(self):
        return self._speed

    def read_speed_percent(self):
        return int(self._speed * 100)

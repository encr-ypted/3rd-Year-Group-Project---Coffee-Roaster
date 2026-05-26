import time

from config import (
    PID_INTEGRAL_LIMIT,
    PID_KD,
    PID_KI,
    PID_KP,
    PID_OUT_MAX,
    PID_OUT_MIN,
)


class PIDController:
    def __init__(
        self,
        kp=PID_KP,
        ki=PID_KI,
        kd=PID_KD,
        out_min=PID_OUT_MIN,
        out_max=PID_OUT_MAX,
        integral_limit=PID_INTEGRAL_LIMIT,
    ):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.out_min = out_min
        self.out_max = out_max
        self.integral_limit = integral_limit
        self._integral = 0.0
        self._previous_error = 0.0
        self.previous_time = None

    def reset(self):
        self._integral = 0.0
        self._previous_error = 0.0
        self.previous_time = None

    def as_dict(self) -> dict:
        return {
            "kp": round(self.kp, 4),
            "ki": round(self.ki, 4),
            "kd": round(self.kd, 4),
        }

    @classmethod
    def default_gains(cls) -> dict:
        return {"kp": PID_KP, "ki": PID_KI, "kd": PID_KD}

    def set_gains(
        self,
        kp: float | None = None,
        ki: float | None = None,
        kd: float | None = None,
        *,
        reset: bool = False,
    ) -> dict:
        if kp is not None:
            self.kp = max(0.0, min(float(kp), 50.0))
        if ki is not None:
            self.ki = max(0.0, min(float(ki), 5.0))
        if kd is not None:
            self.kd = max(0.0, min(float(kd), 20.0))
        if reset:
            self.reset()
        return self.as_dict()

    def calculate(self, setpoint, measurement):
        current_time = time.time()
        error = setpoint - measurement

        if self.previous_time is None:
            dt = 0.1
        else:
            dt = max(current_time - self.previous_time, 0.001)

        p = self.kp * error

        self._integral += error * dt
        self._integral = max(
            -self.integral_limit,
            min(self.integral_limit, self._integral),
        )

        derivative = (error - self._previous_error) / dt
        i = self.ki * self._integral
        d = self.kd * derivative

        self._previous_error = error
        self.previous_time = current_time

        output = p + i + d
        return max(self.out_min, min(self.out_max, output))

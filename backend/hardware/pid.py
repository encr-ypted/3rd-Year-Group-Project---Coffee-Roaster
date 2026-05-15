import time

class PIDController:
    def __init__(
        self, kp = 4.0, ki = 0.05, kd = 1.5, out_min = 0.0, out_max = 100.0, integral_limit = 500.0):
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

        derivative = ((error - self._previous_error) / dt)

        i = self.ki * self._integral

        d = self.kd * derivative

        self._previous_error = error
        self.previous_time = current_time

        output = p + i + d
        return max(self.out_min, min(self.out_max, output))

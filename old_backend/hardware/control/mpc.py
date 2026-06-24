"""
Model-predictive heater control — params from config.py.

Predicts temperature over a horizon for each candidate duty cycle and picks
the duty that minimises tracking error, overshoot, and abrupt heater changes.
"""

from config import (
    MAX_SAFE_TEMP_C,
    MPC_AMBIENT_C,
    MPC_DUTY_STEP,
    MPC_MODEL_A,
    MPC_MODEL_B,
    MPC_OUT_MAX,
    MPC_OUT_MIN,
    MPC_OVERSHOOT_BAND_C,
    MPC_PREDICTION_HORIZON,
    MPC_UNSAFE_PENALTY,
    MPC_WEIGHT_HEATER_CHG,
    MPC_WEIGHT_OVERSHOOT,
    MPC_WEIGHT_TRACKING,
)


class MPCController:
    def __init__(
        self,
        ambient_c=MPC_AMBIENT_C,
        model_a=MPC_MODEL_A,
        model_b=MPC_MODEL_B,
        horizon=MPC_PREDICTION_HORIZON,
        duty_step=MPC_DUTY_STEP,
        weight_tracking=MPC_WEIGHT_TRACKING,
        weight_heater_chg=MPC_WEIGHT_HEATER_CHG,
        weight_overshoot=MPC_WEIGHT_OVERSHOOT,
        overshoot_band_c=MPC_OVERSHOOT_BAND_C,
        out_min=MPC_OUT_MIN,
        out_max=MPC_OUT_MAX,
    ):
        self.ambient_c = ambient_c
        self.model_a = model_a
        self.model_b = model_b
        self.horizon = int(horizon)
        self.duty_step = max(1, int(duty_step))
        self.weight_tracking = weight_tracking
        self.weight_heater_chg = weight_heater_chg
        self.weight_overshoot = weight_overshoot
        self.overshoot_band_c = overshoot_band_c
        self.out_min = out_min
        self.out_max = out_max
        self.previous_output = 0.0

    def reset(self):
        self.previous_output = 0.0

    def get_mpc_config(self):
        return {
            "ambient_c": self.ambient_c,
            "model_a": round(self.model_a, 6),
            "model_b": round(self.model_b, 6),
            "horizon": self.horizon,
            "duty_step": self.duty_step,
            "weight_tracking": round(self.weight_tracking, 4),
            "weight_heater_chg": round(self.weight_heater_chg, 4),
            "weight_overshoot": round(self.weight_overshoot, 4),
            "overshoot_band_c": self.overshoot_band_c,
        }

    def set_params(
        self,
        weight_tracking=None,
        weight_heater_chg=None,
        weight_overshoot=None,
        horizon=None,
        model_a=None,
        model_b=None,
        reset=False,
    ):
        if weight_tracking is not None:
            self.weight_tracking = max(0.0, float(weight_tracking))
        if weight_heater_chg is not None:
            self.weight_heater_chg = max(0.0, float(weight_heater_chg))
        if weight_overshoot is not None:
            self.weight_overshoot = max(0.0, float(weight_overshoot))
        if horizon is not None:
            self.horizon = max(1, int(horizon))
        if model_a is not None:
            self.model_a = float(model_a)
        if model_b is not None:
            self.model_b = float(model_b)
        if reset:
            self.reset()
        return self.get_mpc_config()

    def calculate(self, setpoint, measurement):
        temp_c = float(measurement)
        target_c = float(setpoint)

        best_duty = 0.0
        best_cost = float("inf")
        prev = self.previous_output

        for duty in range(0, 101, self.duty_step):
            predicted_temp = temp_c
            cost = 0.0

            for _ in range(self.horizon):
                predicted_temp = (
                    self.ambient_c
                    + self.model_a * (predicted_temp - self.ambient_c)
                    + self.model_b * duty
                )

                error = target_c - predicted_temp
                cost += self.weight_tracking * (error ** 2)

                if predicted_temp > target_c + self.overshoot_band_c:
                    cost += self.weight_overshoot * (
                        (predicted_temp - target_c) ** 2
                    )

                if predicted_temp > MAX_SAFE_TEMP_C:
                    cost += MPC_UNSAFE_PENALTY

            cost += self.weight_heater_chg * ((duty - prev) ** 2)

            if cost < best_cost:
                best_cost = cost
                best_duty = float(duty)

        self.previous_output = best_duty
        return max(self.out_min, min(self.out_max, best_duty))

"""Factory for roast/bench heater control (MPC or legacy PID)."""

import config as cfg
from hardware.control.mpc import MPCController
from hardware.control.pid import PIDController


def create_heater_controller(mode=None):
    chosen = (mode or getattr(cfg, "HEATER_CONTROLLER", "mpc")).lower()
    if chosen == "pid":
        return PIDController()
    return MPCController()

"""
Sigmoid roast setpoint ramp.

    setpoint(t) = (target - start) / (1 + exp(-steepness * (t_min - midpoint_min))) + start

Same shape as the prototype: 80 / (1 + exp(-(t - 2))) + 160, but scaled from the
actual bean start temperature up to each profile's target_c.
"""

import math


def effective_setpoint(
    start_temp_c,
    final_target_c,
    elapsed_s,
    midpoint_min,
    steepness=1.0,
):
    start = float(start_temp_c)
    target = float(final_target_c)
    midpoint_min = float(midpoint_min)
    steepness = float(steepness)

    if target <= start:
        return target

    t_min = max(0.0, float(elapsed_s)) / 60.0
    span = target - start
    ramped = span / (1.0 + math.exp(-steepness * (t_min - midpoint_min))) + start
    return min(ramped, target)

"""
Sigmoid roast setpoint ramp.

Base logistic (minutes):

    raw(t) = (target - start) / (1 + exp(-steepness * (t - midpoint))) + start

Remapped so setpoint(0) == start (bean temp at roast start) and still reaches target.
Without anchoring, raw(0) sits above start and the chart looks misaligned early on.
"""

import math


def _logistic_setpoint(start, target, t_min, midpoint_min, steepness):
    span = target - start
    return span / (1.0 + math.exp(-steepness * (t_min - midpoint_min))) + start


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
    at_zero = _logistic_setpoint(start, target, 0.0, midpoint_min, steepness)
    raw = _logistic_setpoint(start, target, t_min, midpoint_min, steepness)

    if target <= at_zero or abs(target - at_zero) < 1e-9:
        return min(raw, target)

    remapped = start + (raw - at_zero) / (target - at_zero) * (target - start)
    return min(remapped, target)

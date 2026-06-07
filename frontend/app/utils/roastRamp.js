/** Matches backend/hardware/control/roast_ramp.py */

function logisticSetpoint(start, target, tMin, mid, k) {
  const span = target - start
  return span / (1 + Math.exp(-k * (tMin - mid))) + start
}

/** Anchored sigmoid: setpoint at t=0 equals bean start temp, still reaches target. */
export function sigmoidSetpoint(startTemp, targetTemp, elapsedSec, midpointMin, steepness = 1) {
  const start = Number(startTemp)
  const target = Number(targetTemp)
  const mid = Number(midpointMin)
  const k = Number(steepness)

  if (target <= start) return target

  const tMin = Math.max(0, Number(elapsedSec)) / 60
  const atZero = logisticSetpoint(start, target, 0, mid, k)
  const raw = logisticSetpoint(start, target, tMin, mid, k)

  if (target <= atZero || Math.abs(target - atZero) < 1e-9) {
    return Math.min(raw, target)
  }

  const remapped = start + ((raw - atZero) / (target - atZero)) * (target - start)
  return Math.min(remapped, target)
}

/** Seconds until the planned curve is within 0.5°C of target. */
export function estimateRoastDurationSec(startTemp, targetTemp, midpointMin, steepness = 1) {
  for (let sec = 0; sec <= 30 * 60; sec += 15) {
    if (sigmoidSetpoint(startTemp, targetTemp, sec, midpointMin, steepness) >= targetTemp - 0.5) {
      return sec
    }
  }
  return 12 * 60
}

export function buildPlannedTrajectory(plan, stepSec = 20) {
  if (!plan?.target || plan.startTemp == null) return []

  const start = plan.startTemp
  const target = plan.target
  const mid = plan.midpointMin ?? 2
  const k = plan.steepness ?? 1

  const durationSec = estimateRoastDurationSec(start, target, mid, k)

  const points = []
  for (let t = 0; t <= durationSec; t += stepSec) {
    points.push({
      x: t,
      y: sigmoidSetpoint(start, target, t, mid, k),
    })
  }
  return points
}

/** Plan params aligned with the latest telemetry sample during an active roast. */
export function planFromTelemetry(plan, points) {
  if (!plan) return null
  const last = points?.[points.length - 1]
  if (!last) return plan

  return {
    startTemp: plan.startTemp,
    target: last.targetTemp ?? plan.target,
    midpointMin: last.rampMidpointMin ?? plan.midpointMin ?? 2,
    steepness: last.rampSteepness ?? plan.steepness ?? 1,
  }
}

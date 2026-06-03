/** Matches backend/hardware/roast_ramp.py */

export function sigmoidSetpoint(startTemp, targetTemp, elapsedSec, midpointMin, steepness = 1) {
  const start = Number(startTemp)
  const target = Number(targetTemp)
  const mid = Number(midpointMin)
  const k = Number(steepness)

  if (target <= start) return target

  const tMin = Math.max(0, Number(elapsedSec)) / 60
  const span = target - start
  const ramped = span / (1 + Math.exp(-k * (tMin - mid))) + start
  return Math.min(ramped, target)
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

  const durationSec = estimateRoastDurationSec(
    plan.startTemp,
    plan.target,
    plan.midpointMin ?? 2,
    plan.steepness ?? 1,
  )

  const points = []
  for (let t = 0; t <= durationSec; t += stepSec) {
    points.push({
      x: t,
      y: sigmoidSetpoint(
        plan.startTemp,
        plan.target,
        t,
        plan.midpointMin ?? 2,
        plan.steepness ?? 1,
      ),
    })
  }
  return points
}

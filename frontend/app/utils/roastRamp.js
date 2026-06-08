

export function sigmoidSetpoint(startTemp, targetTemp, elapsedSec, midpointMin, steepness = 1) {
  const start = Number(startTemp)
  const target = Number(targetTemp)
  const mid = Number(midpointMin)
  const k = Number(steepness)

  if (target <= start) return target

  const tMin = Math.max(0, Number(elapsedSec)) / 60

  const rawZero = (target - start) / (1 + Math.exp(-k * (0 - mid))) + start
  const rawNow = (target - start) / (1 + Math.exp(-k * (tMin - mid))) + start

  const setpoint = start + ((rawNow - rawZero) / (target - rawZero)) * (target - start)

  return Math.min(setpoint, target)
}

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
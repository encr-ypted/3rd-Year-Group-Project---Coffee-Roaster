/**
 * Exponential moving average over {x, y} points (display-only smoothing).
 * @param {Array<{x: number, y: number}>} points - sorted by x
 * @param {number} alpha - weight on newest sample (0–1); lower = smoother
 */
export function emaSmooth(points, alpha = 0.35) {
  if (!points?.length) return []
  if (points.length === 1) return [{ ...points[0] }]

  const out = [{ ...points[0] }]
  for (let i = 1; i < points.length; i++) {
    const prevY = out[i - 1].y
    const y = alpha * points[i].y + (1 - alpha) * prevY
    out.push({ x: points[i].x, y })
  }
  return out
}
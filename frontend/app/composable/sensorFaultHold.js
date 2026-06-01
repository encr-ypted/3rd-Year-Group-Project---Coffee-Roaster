/** Keep the last thermocouple fault visible after reads recover. */
export const SENSOR_FAULT_HOLD_MS = 15000

export function createSensorFaultHold() {
  let clearTimer = null
  let lastFault = null

  function apply(setValue, fault) {
    if (fault) {
      if (clearTimer) {
        clearTimeout(clearTimer)
        clearTimer = null
      }
      lastFault = fault
      setValue(fault)
      return
    }

    if (!lastFault) {
      setValue(null)
      return
    }

    setValue(lastFault)
    if (clearTimer) return

    clearTimer = setTimeout(() => {
      lastFault = null
      setValue(null)
      clearTimer = null
    }, SENSOR_FAULT_HOLD_MS)
  }

  function reset(setValue) {
    if (clearTimer) clearTimeout(clearTimer)
    clearTimer = null
    lastFault = null
    setValue(null)
  }

  return { apply, reset }
}

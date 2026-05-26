import { ref } from 'vue'

const BENCH_WS_URL = 'ws://10.115.50.98:8001/ws/bench'

const socket = ref(null)
const isConnected = ref(false)
const lastError = ref(null)
const lastResult = ref(null)
const sessionActive = ref(false)
const lastTelemetryAt = ref(null)

const live = ref({
  temp: null,
  tempRaw: null,
  sensorFault: null,
  heaterPwm: 0,
  fanPwm: 0,
})

let reconnectTimer = null

const applyTelemetry = (message) => {
  live.value = {
    temp: message.temp ?? live.value.temp,
    tempRaw: message.temp_raw ?? message.tempRaw ?? live.value.tempRaw,
    sensorFault:
      message.sensor_fault !== undefined
        ? message.sensor_fault
        : message.sensorFault !== undefined
          ? message.sensorFault
          : live.value.sensorFault,
    heaterPwm: message.heater_pwm ?? message.heaterPwm ?? live.value.heaterPwm,
    fanPwm: message.fan_pwm ?? message.fanPwm ?? live.value.fanPwm,
  }
  if (message.session_active !== undefined) {
    sessionActive.value = message.session_active
  }
  lastTelemetryAt.value = Date.now()
}

const sendJson = (payload) => {
  if (!socket.value || socket.value.readyState !== WebSocket.OPEN) return false
  socket.value.send(JSON.stringify(payload))
  return true
}

export const useHardwareTest = () => {
  const isStreaming = computed(() => {
    if (!isConnected.value || !lastTelemetryAt.value) return false
    return Date.now() - lastTelemetryAt.value < 2500
  })

  const connect = () => {
    if (socket.value?.readyState === WebSocket.OPEN) return

    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }

    socket.value = new WebSocket(BENCH_WS_URL)

    socket.value.onopen = () => {
      isConnected.value = true
      lastError.value = null
    }

    socket.value.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)

        if (message.type === 'bench_telemetry') {
          applyTelemetry(message)
        } else if (message.type === 'bench_result') {
          lastResult.value = message
          if (message.temp !== undefined || message.temp_raw !== undefined) {
            applyTelemetry(message)
          } else if (message.sensors) {
            applyTelemetry({
              temp: message.sensors.temp_c,
              temp_raw: message.sensors.temp_raw_c,
              heater_pwm: message.sensors.heater_pwm,
              fan_pwm: message.sensors.fan_pwm,
              session_active: message.sensors.session_active,
            })
          }
          if (message.session_active !== undefined) {
            sessionActive.value = message.session_active
          }
        } else if (message.type === 'error') {
          lastError.value = message.msg
        } else if (message.type === 'bench_ready') {
          lastResult.value = message
        }
      } catch (e) {
        console.error('Bench WebSocket parse error:', e)
      }
    }

    socket.value.onclose = () => {
      isConnected.value = false
      sessionActive.value = false
      lastTelemetryAt.value = null
      socket.value = null
      reconnectTimer = setTimeout(connect, 3000)
    }

    socket.value.onerror = () => {
      isConnected.value = false
      lastError.value =
        'Bench server not reachable (run: python api/hardware_test.py on port 8001)'
    }
  }

  const disconnect = () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    socket.value?.close()
  }

  const send = (action, extra = {}) => {
    if (!sendJson({ action, ...extra })) {
      lastError.value = 'Not connected to bench API (port 8001)'
    }
  }

  return {
    connect,
    disconnect,
    isConnected,
    isStreaming,
    lastError,
    lastResult,
    lastTelemetryAt,
    sessionActive,
    live,
    startSession: () => send('SESSION_START'),
    stopSession: () => send('SESSION_STOP'),
    emergencyStop: () => send('E_STOP'),
    readSensors: () => send('READ_SENSORS'),
    setFan: (percent) => send('FAN_SET', { percent }),
    stopFan: () => send('FAN_STOP'),
    heaterOn: () => send('HEATER_ON'),
    heaterOff: () => send('HEATER_OFF'),
    heaterPulse: (percent) => send('HEATER_PULSE', { percent }),
  }
}

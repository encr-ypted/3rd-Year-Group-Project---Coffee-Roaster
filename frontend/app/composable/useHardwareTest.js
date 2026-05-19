import { ref } from 'vue'

const BENCH_WS_URL = 'ws://10.64.26.141:8001/ws/bench'

const socket = ref(null)
const isConnected = ref(false)
const lastError = ref(null)
const lastResult = ref(null)
const sessionActive = ref(false)

const live = ref({
  temp: null,
  tempRaw: null,
  heaterPwm: 0,
  fanPwm: 0,
})

const sendJson = (payload) => {
  if (!socket.value || socket.value.readyState !== WebSocket.OPEN) return false
  socket.value.send(JSON.stringify(payload))
  return true
}

export const useHardwareTest = () => {
  const connect = () => {
    if (socket.value?.readyState === WebSocket.OPEN) return

    socket.value = new WebSocket(BENCH_WS_URL)

    socket.value.onopen = () => {
      isConnected.value = true
      lastError.value = null
    }

    socket.value.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)

        if (message.type === 'bench_telemetry') {
          live.value = {
            temp: message.temp,
            tempRaw: message.temp_raw,
            heaterPwm: message.heater_pwm,
            fanPwm: message.fan_pwm,
          }
          sessionActive.value = message.session_active
        } else if (message.type === 'bench_result') {
          lastResult.value = message
          if (message.session_active !== undefined) {
            sessionActive.value = message.session_active
          }
          if (message.sensors) {
            live.value.temp = message.sensors.temp_c
            live.value.tempRaw = message.sensors.temp_raw_c
            live.value.heaterPwm = message.sensors.heater_pwm
            live.value.fanPwm = message.sensors.fan_pwm
          }
          if (message.heater_pwm !== undefined) {
            live.value.heaterPwm = message.heater_pwm
          }
          if (message.fan_pwm !== undefined) {
            live.value.fanPwm = message.fan_pwm
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
      socket.value = null
    }

    socket.value.onerror = () => {
      isConnected.value = false
      lastError.value = 'Bench server not reachable (run: python api/hardware_test.py on port 8001)'
    }
  }

  const disconnect = () => socket.value?.close()

  const send = (action, extra = {}) => {
    if (!sendJson({ action, ...extra })) {
      lastError.value = 'Not connected to bench API (port 8001)'
    }
  }

  return {
    connect,
    disconnect,
    isConnected,
    lastError,
    lastResult,
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

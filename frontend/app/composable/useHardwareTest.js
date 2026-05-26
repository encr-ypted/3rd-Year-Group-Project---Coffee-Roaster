import { ref } from 'vue'



const BENCH_WS_URL = 'ws://10.138.72.98:8001/ws/bench'



const socket = ref(null)

const isConnected = ref(false)

const lastError = ref(null)

const lastResult = ref(null)

const sessionActive = ref(false)

const lastTelemetryAt = ref(null)



const live = ref({

  temp: null,

  sensorFault: null,

  heaterPwm: 0,

  heaterMode: 'off',

  pidActive: false,

  pidTarget: null,

  pidKp: null,

  pidKi: null,

  pidKd: null,

  fanPwm: 0,

})



let reconnectTimer = null



const applyTelemetry = (message) => {

  live.value = {

    temp: message.temp ?? live.value.temp,

    sensorFault:

      message.sensor_fault !== undefined

        ? message.sensor_fault

        : message.sensorFault !== undefined

          ? message.sensorFault

          : live.value.sensorFault,

    heaterPwm: message.heater_pwm ?? message.heaterPwm ?? live.value.heaterPwm,

    heaterMode:

      message.heater_mode ?? message.heaterMode ?? live.value.heaterMode,

    pidActive:

      message.pid_active ?? message.pidActive ?? live.value.pidActive,

    pidTarget:

      message.pid_target !== undefined

        ? message.pid_target

        : message.pidTarget !== undefined

          ? message.pidTarget

          : live.value.pidTarget,

    pidKp:
      message.pid_kp ?? message.kp ?? live.value.pidKp,

    pidKi:
      message.pid_ki ?? message.ki ?? live.value.pidKi,

    pidKd:
      message.pid_kd ?? message.kd ?? live.value.pidKd,

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

          if (message.ok === false && message.error) {
            lastError.value = message.error
          }

          if (

            message.temp !== undefined ||

            message.pid_active !== undefined ||

            message.pid_target !== undefined ||

            message.pid_kp !== undefined ||

            message.kp !== undefined

          ) {

            applyTelemetry(message)

          } else if (message.sensors) {

            applyTelemetry({

              temp: message.sensors.temp_c,

              heater_pwm: message.sensors.heater_pwm,

              fan_pwm: message.sensors.fan_pwm,

              session_active: message.sensors.session_active,

            })

          }

          if (message.session_active !== undefined) {

            sessionActive.value = message.session_active

          }

          if (message.pid_active !== undefined) {

            live.value.pidActive = message.pid_active

          }

        } else if (message.type === 'error') {

          lastError.value = message.msg

        } else if (message.type === 'bench_ready') {

          lastResult.value = message

          applyTelemetry(message)

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

    setFan: (percent) => send('FAN_SET', { percent }),

    stopFan: () => send('FAN_STOP'),

    heatToTarget: (targetTemp) =>

      send('HEAT_TO_TARGET', { target_temp: targetTemp }),

    stopHeating: () => send('HEAT_STOP'),

    setTarget: (targetTemp) =>

      send('SET_TARGET', { target_temp: targetTemp }),

    getPidGains: () => send('GET_PID_GAINS'),

    setPidGains: (kp, ki, kd, resetIntegral = false) =>

      send('SET_PID_GAINS', {

        kp,

        ki,

        kd,

        reset_integral: resetIntegral,

      }),

  }

}



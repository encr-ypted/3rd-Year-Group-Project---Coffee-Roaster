import { ref } from 'vue'

import { createSensorFaultHold } from './sensorFaultHold'





const HOST = "coffee:8001"

const BENCH_WS_URL = `ws://${HOST}/ws/bench`;



const socket = ref(null)

const connected = ref(false)

const connectError = ref(null)

const lastAck = ref(null)

const lastTelemetryAt = ref(null)



const live = ref({

  temp: null,

  fanPwm: 0,

  heaterPwm: 0,

  heating: false,

  target: null,

  controller: 'mpc',

  pidKp: 1.8,

  pidKi: 0.09,

  pidKd: 0,

  weightTracking: 5,

  weightHeaterChg: 0.1,

  weightOvershoot: 2,

  horizon: 120,

  sensorFault: null,

})



let reconnectTimer = null

const sensorFaultHold = createSensorFaultHold()



function applySnapshot(msg) {

  if (msg.temp !== undefined) live.value.temp = msg.temp

  if (msg.fan_pwm !== undefined) live.value.fanPwm = msg.fan_pwm

  if (msg.heater_pwm !== undefined) live.value.heaterPwm = msg.heater_pwm

  if (msg.heating !== undefined) live.value.heating = msg.heating

  if (msg.target !== undefined) live.value.target = msg.target

  if (msg.controller !== undefined) live.value.controller = msg.controller

  if (msg.pid_kp !== undefined) live.value.pidKp = msg.pid_kp

  if (msg.pid_ki !== undefined) live.value.pidKi = msg.pid_ki

  if (msg.pid_kd !== undefined) live.value.pidKd = msg.pid_kd

  if (msg.weight_tracking !== undefined) live.value.weightTracking = msg.weight_tracking

  if (msg.weight_heater_chg !== undefined) live.value.weightHeaterChg = msg.weight_heater_chg

  if (msg.weight_overshoot !== undefined) live.value.weightOvershoot = msg.weight_overshoot

  if (msg.horizon !== undefined) live.value.horizon = msg.horizon

  if ('sensor_fault' in msg) {

    sensorFaultHold.apply((v) => { live.value.sensorFault = v }, msg.sensor_fault)

  }

  lastTelemetryAt.value = Date.now()

}



export function useHardwareTest() {

  const streaming = computed(() => {

    if (!connected.value || !lastTelemetryAt.value) return false

    return Date.now() - lastTelemetryAt.value < 2500

  })



  function connect() {

    if (socket.value?.readyState === WebSocket.OPEN) return

    if (reconnectTimer) {

      clearTimeout(reconnectTimer)

      reconnectTimer = null

    }



    socket.value = new WebSocket(BENCH_WS_URL)



    socket.value.onopen = () => {

      connected.value = true

      connectError.value = null

    }



    socket.value.onmessage = (event) => {

      try {

        const msg = JSON.parse(event.data)

        if (msg.type === 'bench_telemetry' || msg.type === 'bench_ready') {

          applySnapshot(msg)

        }

        if (msg.type === 'bench_ack' || msg.type === 'bench_ready') {

          lastAck.value = msg

          applySnapshot(msg)

        }

      } catch (e) {

        console.error('Bench parse error:', e)

      }

    }



    socket.value.onclose = () => {

      connected.value = false

      lastTelemetryAt.value = null

      socket.value = null

      reconnectTimer = setTimeout(connect, 3000)

    }



    socket.value.onerror = () => {

      connected.value = false

      connectError.value = 'Bench offline — run: python api/hardware_test.py on port 8001'

    }

  }



  function disconnect() {

    if (reconnectTimer) {

      clearTimeout(reconnectTimer)

      reconnectTimer = null

    }

    socket.value?.close()

  }



  function send(action, extra = {}) {

    if (!socket.value || socket.value.readyState !== WebSocket.OPEN) {

      connectError.value = 'Not connected to bench (port 8001)'

      return false

    }

    socket.value.send(JSON.stringify({ action, ...extra }))

    return true

  }



  return {

    connect,

    disconnect,

    connected,

    connectError,

    lastAck,

    streaming,

    live,

    setFan: (percent) => send('FAN_SET', { percent }),

    fanOff: () => send('FAN_OFF'),

    heatStart: (target) => send('HEAT_START', { target }),

    heatStop: () => send('HEAT_STOP'),

    setTarget: (target) => send('HEAT_SET_TARGET', { target }),

    pidSet: (kp, ki, kd, resetIntegral = false) =>

      send('PID_SET', { kp, ki, kd, reset_integral: resetIntegral }),

    mpcSet: (weightTracking, weightHeaterChg, weightOvershoot, horizon, reset = false) =>

      send('MPC_SET', {

        weight_tracking: weightTracking,

        weight_heater_chg: weightHeaterChg,

        weight_overshoot: weightOvershoot,

        horizon,

        reset,

      }),

    setController: (mode) => send('SET_CONTROLLER', { mode }),

    getStatus: () => send('GET_STATUS'),

  }

}


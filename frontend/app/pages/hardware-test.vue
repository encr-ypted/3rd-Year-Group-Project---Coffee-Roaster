<script setup>
import { useHardwareTest } from '~/composable/useHardwareTest'

const {
  connect,
  disconnect,
  connected,
  connectError,
  streaming,
  live,
  setFan,
  fanOff,
  heatStart,
  heatStop,
  setTarget,
  pidSet,
  mpcSet,
  setController,
  lastAck,
  getStatus,
} = useHardwareTest()

const target = ref(100)
const fanSpeed = ref(100)
const kp = ref(2.6)
const ki = ref(0.05)
const kd = ref(0)
const resetIntegral = ref(false)
const weightTracking = ref(2)
const weightHeaterChg = ref(0.1)
const weightOvershoot = ref(5)
const horizon = ref(30)
const resetMpc = ref(false)
const defaults = ref({
  kp: 2.6,
  ki: 0.05,
  kd: 0,
  weight_tracking: 2,
  weight_heater_chg: 0.1,
  weight_overshoot: 5,
  horizon: 30,
})

const controllerMode = ref('pid')
const usesMpc = computed(() => controllerMode.value === 'mpc')
const usesPid = computed(() => controllerMode.value === 'pid')

watch(
  () => live.value.controller,
  (mode) => {
    if (mode === 'pid' || mode === 'mpc') controllerMode.value = mode
  },
  { immediate: true },
)

watch(lastAck, (msg) => {
  if (!msg?.defaults) return
  if (msg.defaults.pid) {
    kp.value = msg.defaults.pid.kp ?? kp.value
    ki.value = msg.defaults.pid.ki ?? ki.value
    kd.value = msg.defaults.pid.kd ?? kd.value
  }
  if (msg.defaults.mpc) {
    const m = msg.defaults.mpc
    weightTracking.value = m.weight_tracking ?? weightTracking.value
    weightHeaterChg.value = m.weight_heater_chg ?? weightHeaterChg.value
    weightOvershoot.value = m.weight_overshoot ?? weightOvershoot.value
    horizon.value = m.horizon ?? horizon.value
  }
})

function pickController(mode) {
  if (mode !== 'pid' && mode !== 'mpc') return
  if (!connected.value) {
    controllerMode.value = mode
    return
  }
  setController(mode)
}

watch(
  () => [live.value.pidKp, live.value.pidKi, live.value.pidKd],
  ([a, b, c]) => {
    if (a != null) kp.value = a
    if (b != null) ki.value = b
    if (c != null) kd.value = c
  },
)

watch(
  () => [
    live.value.weightTracking,
    live.value.weightHeaterChg,
    live.value.weightOvershoot,
    live.value.horizon,
  ],
  ([wt, wh, wo, h]) => {
    if (wt != null) weightTracking.value = wt
    if (wh != null) weightHeaterChg.value = wh
    if (wo != null) weightOvershoot.value = wo
    if (h != null) horizon.value = h
  },
)

watch(live, (v) => {
  if (v.target != null && !live.value.heating) target.value = v.target
}, { deep: true })

onMounted(() => connect())
onUnmounted(() => disconnect())

const statusText = computed(() => {
  if (!connected.value) return 'Offline'
  if (live.value.heating) {
    const label = controllerMode.value === 'pid' ? 'PID' : 'MPC'
    return `Heating (${label})`
  }
  if (live.value.fanPwm > 0) return 'Fan on'
  return `Ready · ${controllerMode.value.toUpperCase()}`
})
</script>

<template>
  <div class="min-h-screen w-full max-w-full overflow-x-clip coffee-dark-bg text-zinc-200">
    <header class="border-b border-white/[0.06] bg-[#141210]/90 sticky top-0 z-10">
      <div class="max-w-lg mx-auto px-5 py-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between min-w-0">
        <div class="min-w-0">
          <h1 class="text-lg font-semibold text-white">Hardware bench</h1>
          <p class="text-xs text-zinc-500 break-words">
            Port 8001 · <code class="text-zinc-400 break-all">python api/hardware_test.py</code>
          </p>
        </div>
        <div class="flex items-center gap-3 shrink-0">
          <span
            class="text-xs px-2.5 py-1 rounded-full border"
            :class="connected ? 'border-emerald-500/40 text-emerald-400' : 'border-zinc-600 text-zinc-500'"
          >
            {{ statusText }}
          </span>
          <NuxtLink to="/" class="text-xs text-gold-400 border border-white/10 px-2 py-1 rounded-lg">Dashboard</NuxtLink>
        </div>
      </div>
    </header>

    <main class="max-w-lg mx-auto px-5 py-6 space-y-5">
      <p v-if="connectError" class="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3">
        {{ connectError }}
      </p>
      <p
        v-else-if="live.sensorFault"
        class="text-sm text-amber-300 bg-amber-500/10 border border-amber-500/25 rounded-xl px-4 py-3"
      >
        Thermocouple: {{ live.sensorFault }}
      </p>

      <section class="rounded-2xl border border-white/[0.06] bg-[#1a1714] p-5">
        <div class="flex justify-between items-start mb-4">
          <h2 class="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Temperature</h2>
          <span v-if="streaming" class="text-[10px] text-emerald-400 uppercase">Live</span>
        </div>

        <p class="text-4xl font-bold text-white tabular-nums">
          {{ live.temp != null ? live.temp.toFixed(1) : '—' }}
          <span class="text-lg text-zinc-500 font-normal">°C</span>
        </p>

        <p class="text-xs text-zinc-600 mt-4 pt-3 border-t border-white/[0.06] tabular-nums">
          Heater {{ live.heaterPwm }}%
          <span v-if="live.heating && live.target"> → {{ live.target }}°C</span>
          · Fan {{ live.fanPwm }}%
        </p>
      </section>

      <section class="rounded-2xl border border-orange-500/20 bg-orange-500/5 p-5 space-y-4">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 class="text-xs font-semibold text-orange-300 uppercase tracking-wider">Heater</h2>
            <p class="text-[10px] text-zinc-500 mt-1">
              Bench only — main dashboard uses PID.
            </p>
          </div>
          <div class="grid grid-cols-2 gap-1.5 p-1 rounded-xl bg-black/30 border border-white/10 sm:w-40 shrink-0">
            <button
              type="button"
              class="py-2 rounded-lg text-xs font-semibold transition-colors disabled:opacity-40"
              :class="usesMpc ? 'bg-violet-600 text-white' : 'text-zinc-400 hover:text-white'"
              :disabled="!connected && usesMpc"
              @click="pickController('mpc')"
            >
              MPC
            </button>
            <button
              type="button"
              class="py-2 rounded-lg text-xs font-semibold transition-colors disabled:opacity-40"
              :class="usesPid ? 'bg-violet-600 text-white' : 'text-zinc-400 hover:text-white'"
              :disabled="!connected && usesPid"
              @click="pickController('pid')"
            >
              PID
            </button>
          </div>
        </div>

        <p v-if="lastAck?.error" class="text-xs text-red-400 -mt-2">{{ lastAck.error }}</p>

        <label class="block text-xs text-zinc-500">
          Target °C
          <input
            v-model.number="target"
            type="number"
            min="20"
            max="245"
            class="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-white"
            :disabled="!connected"
          >
        </label>
        <div class="flex gap-2">
          <button
            type="button"
            class="flex-1 py-2.5 rounded-xl text-sm font-semibold bg-orange-600 text-white disabled:opacity-40"
            :disabled="!connected || live.heating"
            @click="heatStart(target)"
          >
            Heat to target
          </button>
          <button
            type="button"
            class="py-2.5 px-4 rounded-xl text-sm border border-white/10 disabled:opacity-40"
            :disabled="!connected || !live.heating"
            @click="heatStop"
          >
            Stop
          </button>
        </div>
        <button
          v-if="live.heating"
          type="button"
          class="text-xs text-orange-300 underline -mt-2"
          @click="setTarget(target)"
        >
          Update target
        </button>

        <div class="pt-4 border-t border-white/[0.08] space-y-3">
          <h3 class="text-[10px] font-semibold text-violet-300 uppercase tracking-wider">
            {{ usesMpc ? 'MPC tuning' : 'PID tuning' }}
          </h3>

          <template v-if="usesMpc">
            <div class="grid grid-cols-2 gap-2">
              <label class="text-xs text-zinc-500">
                Tracking
                <input
                  v-model.number="weightTracking"
                  type="number"
                  step="0.1"
                  min="0"
                  class="mt-1 w-full rounded bg-black/40 border border-white/10 px-2 py-1.5 text-white"
                  :disabled="!connected"
                >
              </label>
              <label class="text-xs text-zinc-500">
                Heater Δ
                <input
                  v-model.number="weightHeaterChg"
                  type="number"
                  step="0.05"
                  min="0"
                  class="mt-1 w-full rounded bg-black/40 border border-white/10 px-2 py-1.5 text-white"
                  :disabled="!connected"
                >
              </label>
              <label class="text-xs text-zinc-500">
                Overshoot
                <input
                  v-model.number="weightOvershoot"
                  type="number"
                  step="0.5"
                  min="0"
                  class="mt-1 w-full rounded bg-black/40 border border-white/10 px-2 py-1.5 text-white"
                  :disabled="!connected"
                >
              </label>
              <label class="text-xs text-zinc-500">
                Horizon
                <input
                  v-model.number="horizon"
                  type="number"
                  step="1"
                  min="5"
                  max="60"
                  class="mt-1 w-full rounded bg-black/40 border border-white/10 px-2 py-1.5 text-white"
                  :disabled="!connected"
                >
              </label>
            </div>
            <label class="flex items-center gap-2 text-xs text-zinc-500">
              <input v-model="resetMpc" type="checkbox" :disabled="!connected">
              Reset previous duty
            </label>
            <button
              type="button"
              class="w-full py-2 rounded-xl text-sm bg-violet-600 text-white disabled:opacity-40"
              :disabled="!connected"
              @click="mpcSet(weightTracking, weightHeaterChg, weightOvershoot, horizon, resetMpc)"
            >
              Apply MPC
            </button>
          </template>

          <template v-else>
            <div class="grid grid-cols-3 gap-2">
              <label class="text-xs text-zinc-500">Kp<input v-model.number="kp" type="number" step="0.1" class="mt-1 w-full rounded bg-black/40 border border-white/10 px-2 py-1.5 text-white" :disabled="!connected"></label>
              <label class="text-xs text-zinc-500">Ki<input v-model.number="ki" type="number" step="0.01" class="mt-1 w-full rounded bg-black/40 border border-white/10 px-2 py-1.5 text-white" :disabled="!connected"></label>
              <label class="text-xs text-zinc-500">Kd<input v-model.number="kd" type="number" step="0.1" class="mt-1 w-full rounded bg-black/40 border border-white/10 px-2 py-1.5 text-white" :disabled="!connected"></label>
            </div>
            <label class="flex items-center gap-2 text-xs text-zinc-500">
              <input v-model="resetIntegral" type="checkbox" :disabled="!connected">
              Reset integral
            </label>
            <button
              type="button"
              class="w-full py-2 rounded-xl text-sm bg-violet-600 text-white disabled:opacity-40"
              :disabled="!connected"
              @click="pidSet(kp, ki, kd, resetIntegral)"
            >
              Apply PID
            </button>
          </template>
        </div>
      </section>

      <section class="rounded-2xl border border-white/[0.06] bg-[#1a1714] p-5 space-y-3">
        <h2 class="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Fan</h2>
        <label class="block text-xs text-zinc-500">
          {{ fanSpeed }}%
          <input v-model.number="fanSpeed" type="range" min="0" max="100" class="w-full mt-2 accent-sky-500" :disabled="!connected">
        </label>
        <div class="flex gap-2">
          <button
            type="button"
            class="flex-1 py-2 rounded-xl text-sm bg-sky-600 text-white disabled:opacity-40"
            :disabled="!connected"
            @click="setFan(fanSpeed)"
          >
            Set fan
          </button>
          <button
            type="button"
            class="py-2 px-4 rounded-xl text-sm border border-white/10 disabled:opacity-40"
            :disabled="!connected"
            @click="fanOff"
          >
            Off
          </button>
        </div>
      </section>
    </main>
  </div>
</template>

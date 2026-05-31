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
  getStatus,
} = useHardwareTest()

const target = ref(100)
const fanSpeed = ref(100)
const kp = ref(2.6)
const ki = ref(0.05)
const kd = ref(0)
const resetIntegral = ref(false)
const defaults = ref({ kp: 2.6, ki: 0.05, kd: 0 })

watch(
  () => [live.value.pidKp, live.value.pidKi, live.value.pidKd],
  ([a, b, c]) => {
    if (a != null) kp.value = a
    if (b != null) ki.value = b
    if (c != null) kd.value = c
  },
)

watch(live, (v) => {
  if (v.target != null && !live.value.heating) target.value = v.target
}, { deep: true })

onMounted(() => connect())
onUnmounted(() => disconnect())

const statusText = computed(() => {
  if (!connected.value) return 'Offline'
  if (live.value.heating) return 'Heating'
  if (live.value.fanPwm > 0) return 'Fan on'
  return 'Ready'
})
</script>

<template>
  <div class="min-h-screen coffee-dark-bg text-zinc-200">
    <header class="border-b border-white/[0.06] bg-[#141210]/90 sticky top-0 z-10">
      <div class="max-w-lg mx-auto px-5 py-4 flex items-center justify-between">
        <div>
          <h1 class="text-lg font-semibold text-white">Hardware bench</h1>
          <p class="text-xs text-zinc-500">Port 8001 · <code class="text-zinc-400">python api/hardware_test.py</code></p>
        </div>
        <div class="flex items-center gap-3">
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

      <section class="rounded-2xl border border-white/[0.06] bg-[#1a1714] p-5">
        <div class="flex justify-between items-start mb-3">
          <h2 class="text-xs font-semibold text-zinc-400 uppercase tracking-wider">Temperature</h2>
          <span v-if="streaming" class="text-[10px] text-emerald-400 uppercase">Live</span>
        </div>
        <p class="text-4xl font-bold text-white tabular-nums">
          {{ live.temp != null ? live.temp.toFixed(1) : '—' }}
          <span class="text-lg text-zinc-500 font-normal">°C</span>
        </p>
        <p class="text-xs text-zinc-600 mt-2 tabular-nums">
          Heater {{ live.heaterPwm }}%
          <span v-if="live.heating && live.target"> → {{ live.target }}°C</span>
          · Fan {{ live.fanPwm }}%
        </p>
      </section>

      <section class="rounded-2xl border border-orange-500/20 bg-orange-500/5 p-5 space-y-3">
        <h2 class="text-xs font-semibold text-orange-300 uppercase tracking-wider">Heater</h2>
        <label class="block text-xs text-zinc-500">
          Target °C
          <input
            v-model.number="target"
            type="number"
            min="20"
            max="245"
            class="mt-1 w-full rounded-lg bg-black/40 border border-white/10 px-3 py-2 text-white tabular-nums"
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
            Stop heating
          </button>
        </div>
        <p class="text-[10px] text-zinc-600">Stops PID and relay. Fan is unchanged.</p>
        <button
          v-if="live.heating"
          type="button"
          class="text-xs text-orange-300 underline"
          @click="setTarget(target)"
        >
          Update target
        </button>
      </section>

      <section class="rounded-2xl border border-violet-500/20 bg-violet-500/5 p-5 space-y-3">
        <h2 class="text-xs font-semibold text-violet-300 uppercase tracking-wider">PID</h2>
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

<script setup>
import { useHardwareTest } from '~/composable/useHardwareTest'

const {
  connect,
  disconnect,
  isConnected,
  lastError,
  lastResult,
  sessionActive,
  live,
  startSession,
  stopSession,
  emergencyStop,
  readSensors,
  setFan,
  stopFan,
  heaterOn,
  heaterOff,
  heaterPulse,
} = useHardwareTest()

const fanPercent = ref(100)
const heaterPulsePercent = ref(50)

onMounted(() => connect())
onUnmounted(() => disconnect())

const statusLabel = computed(() => {
  if (!isConnected.value) return 'Bench offline'
  return sessionActive.value ? 'Session active' : 'Connected — start session'
})
</script>

<template>
  <div class="min-h-screen coffee-dark-bg text-zinc-200">
    <header class="border-b border-white/[0.06] bg-[#141210]/90 backdrop-blur-sm sticky top-0 z-10">
      <div class="max-w-3xl mx-auto px-5 py-4 flex items-center justify-between gap-4">
        <div>
          <h1 class="text-lg font-semibold text-white tracking-tight">Hardware bench test</h1>
          <p class="text-xs text-zinc-500 mt-0.5">
            Separate API · port <span class="font-mono text-zinc-400">8001</span>
          </p>
        </div>
        <div class="flex items-center gap-3">
          <span
            class="inline-flex items-center gap-2 text-xs font-medium px-3 py-1.5 rounded-full border"
            :class="isConnected ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400' : 'border-zinc-600 bg-zinc-800 text-zinc-400'"
          >
            <span class="w-1.5 h-1.5 rounded-full" :class="isConnected ? 'bg-emerald-400' : 'bg-zinc-500'" />
            {{ statusLabel }}
          </span>
          <NuxtLink
            to="/"
            class="text-xs text-gold-400 hover:text-gold-300 px-3 py-1.5 rounded-lg border border-white/[0.08]"
          >
            Dashboard
          </NuxtLink>
        </div>
      </div>
    </header>

    <main class="max-w-3xl mx-auto px-5 py-8 space-y-6">
      <div class="rounded-2xl border border-amber-500/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-200/90 space-y-2">
        <p>
          <strong>Run on the Pi:</strong>
          <code class="text-xs bg-black/30 px-1.5 py-0.5 rounded ml-1">python api/hardware_test.py</code>
        </p>
        <p class="text-xs text-amber-200/70">
          Do not run <code class="bg-black/30 px-1 rounded">api/main.py</code> at the same time — both need GPIO.
          Use this page for wiring checks; use the dashboard for roasts.
        </p>
      </div>

      <p v-if="lastError" class="text-sm text-red-400 rounded-xl bg-red-500/10 border border-red-500/20 px-4 py-3">
        {{ lastError }}
      </p>

      <section class="rounded-2xl border border-white/[0.06] bg-[#1a1714] p-5 space-y-4">
        <h2 class="text-sm font-semibold text-zinc-300 uppercase tracking-wider">Session</h2>
        <div class="flex flex-wrap gap-3">
          <button
            type="button"
            class="px-4 py-2.5 rounded-xl text-sm font-medium bg-gold-600 hover:bg-gold-500 text-white disabled:opacity-40"
            :disabled="!isConnected || sessionActive"
            @click="startSession"
          >
            Start session
          </button>
          <button
            type="button"
            class="px-4 py-2.5 rounded-xl text-sm font-medium border border-white/10 hover:bg-white/5 disabled:opacity-40"
            :disabled="!isConnected || !sessionActive"
            @click="stopSession"
          >
            Stop session
          </button>
          <button
            type="button"
            class="px-4 py-2.5 rounded-xl text-sm font-bold bg-red-600 hover:bg-red-500 text-white ml-auto disabled:opacity-40"
            :disabled="!isConnected"
            @click="emergencyStop"
          >
            E-STOP
          </button>
        </div>
      </section>

      <section class="rounded-2xl border border-white/[0.06] bg-[#1a1714] p-5 space-y-4">
        <h2 class="text-sm font-semibold text-zinc-300 uppercase tracking-wider">Thermocouple</h2>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <p class="text-xs text-zinc-500 mb-1">Filtered</p>
            <p class="text-3xl font-bold text-white tabular-nums">
              {{ live.temp != null ? live.temp.toFixed(1) : '—' }}
              <span class="text-lg text-zinc-500 font-normal">°C</span>
            </p>
          </div>
          <div>
            <p class="text-xs text-zinc-500 mb-1">Outputs</p>
            <p class="text-sm text-zinc-400 mt-2">
              Fan {{ live.fanPwm }}% · Heater {{ live.heaterPwm }}%
            </p>
          </div>
        </div>
        <button
          type="button"
          class="px-4 py-2 rounded-xl text-sm border border-white/10 hover:bg-white/5 disabled:opacity-40"
          :disabled="!isConnected"
          @click="readSensors"
        >
          Read sensors now
        </button>
        <p v-if="live.tempRaw != null" class="text-xs text-zinc-600 font-mono">
          Raw: {{ live.tempRaw }} °C
        </p>
      </section>

      <section class="rounded-2xl border border-white/[0.06] bg-[#1a1714] p-5 space-y-4">
        <h2 class="text-sm font-semibold text-zinc-300 uppercase tracking-wider">Fan (L298N)</h2>
        <label class="block text-xs text-zinc-500">
          Speed {{ fanPercent }}%
          <input v-model.number="fanPercent" type="range" min="0" max="100" class="w-full mt-2 accent-sky-500" :disabled="!sessionActive">
        </label>
        <div class="flex flex-wrap gap-3">
          <button
            type="button"
            class="px-4 py-2 rounded-xl text-sm bg-sky-600 hover:bg-sky-500 text-white disabled:opacity-40"
            :disabled="!isConnected || !sessionActive"
            @click="setFan(fanPercent)"
          >
            Apply fan speed
          </button>
          <button
            type="button"
            class="px-4 py-2 rounded-xl text-sm border border-white/10 hover:bg-white/5 disabled:opacity-40"
            :disabled="!isConnected || !sessionActive"
            @click="stopFan"
          >
            Fan off
          </button>
        </div>
      </section>

      <section class="rounded-2xl border border-white/[0.06] bg-[#1a1714] p-5 space-y-4">
        <h2 class="text-sm font-semibold text-zinc-300 uppercase tracking-wider">Heater (relay)</h2>
        <p class="text-xs text-zinc-500">
          <strong>On</strong> holds the relay closed (brief tests only).
          <strong>Pulse</strong> runs one 2 s proportional window.
        </p>
        <div class="flex flex-wrap gap-3">
          <button
            type="button"
            class="px-4 py-2 rounded-xl text-sm bg-orange-600 hover:bg-orange-500 text-white disabled:opacity-40"
            :disabled="!isConnected || !sessionActive"
            @click="heaterOn"
          >
            Heater ON
          </button>
          <button
            type="button"
            class="px-4 py-2 rounded-xl text-sm border border-white/10 hover:bg-white/5 disabled:opacity-40"
            :disabled="!isConnected || !sessionActive"
            @click="heaterOff"
          >
            Heater OFF
          </button>
        </div>
        <label class="block text-xs text-zinc-500">
          Pulse {{ heaterPulsePercent }}%
          <input v-model.number="heaterPulsePercent" type="range" min="0" max="100" class="w-full mt-2 accent-orange-500" :disabled="!sessionActive">
        </label>
        <button
          type="button"
          class="px-4 py-2 rounded-xl text-sm bg-orange-600/80 hover:bg-orange-500 text-white disabled:opacity-40"
          :disabled="!isConnected || !sessionActive"
          @click="heaterPulse(heaterPulsePercent)"
        >
          Run one heater pulse
        </button>
      </section>

      <p v-if="lastResult?.note" class="text-xs text-center text-zinc-600">
        {{ lastResult.note }}
      </p>
    </main>
  </div>
</template>

<script setup>

import { useHardwareTest } from '~/composable/useHardwareTest'



const {

  connect,

  disconnect,

  isConnected,

  isStreaming,

  lastError,

  lastResult,

  sessionActive,

  live,

  startSession,

  stopSession,

  emergencyStop,

  setFan,

  stopFan,

  heatToTarget,

  stopHeating,

  setTarget,

  setPidGains,

  getPidGains,

} = useHardwareTest()



const fanPercent = ref(100)

const targetInput = ref(100)

const pidKpInput = ref(2.6)

const pidKiInput = ref(0.05)

const pidKdInput = ref(0)

const resetPidIntegral = ref(false)

const pidDefaults = ref({ kp: 2.6, ki: 0.05, kd: 0 })



watch(

  () => [live.value.pidKp, live.value.pidKi, live.value.pidKd],

  ([kp, ki, kd]) => {

    if (kp != null) pidKpInput.value = kp

    if (ki != null) pidKiInput.value = ki

    if (kd != null) pidKdInput.value = kd

  },

)



watch(lastResult, (msg) => {

  if (msg?.pid_defaults) pidDefaults.value = msg.pid_defaults

})



const tempError = computed(() => {

  if (live.value.temp == null || live.value.pidTarget == null) return null

  return live.value.pidTarget - live.value.temp

})



const heaterStatus = computed(() => {

  if (live.value.heaterMode === 'ramp') return 'Full power → target'

  if (live.value.heaterMode === 'pid') return 'PID holding'

  if (live.value.pidActive) return 'Heating'

  return 'Off'

})



onMounted(() => connect())

onUnmounted(() => disconnect())



const statusLabel = computed(() => {

  if (!isConnected.value) return 'Bench offline'

  if (live.value.pidActive) return heaterStatus.value

  return sessionActive.value ? 'Session active' : 'Connected'

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

        </p>

      </div>



      <p v-if="lastError" class="text-sm text-red-400 rounded-xl bg-red-500/10 border border-red-500/20 px-4 py-3">

        {{ lastError }}

      </p>



      <section class="rounded-2xl border border-white/[0.06] bg-[#1a1714] p-5 space-y-4">

        <div class="flex items-center justify-between gap-3">

          <h2 class="text-sm font-semibold text-zinc-300 uppercase tracking-wider">Temperature</h2>

          <span

            v-if="isConnected"

            class="inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider px-2 py-1 rounded-full"

            :class="isStreaming ? 'text-emerald-400 bg-emerald-500/10' : 'text-zinc-500 bg-zinc-800'"

          >

            <span

              class="w-1.5 h-1.5 rounded-full"

              :class="isStreaming ? 'bg-emerald-400 animate-pulse' : 'bg-zinc-500'"

            />

            {{ isStreaming ? 'Live' : 'Waiting…' }}

          </span>

        </div>

        <p

          v-if="live.sensorFault"

          class="text-xs text-amber-300 rounded-lg bg-amber-500/10 border border-amber-500/25 px-3 py-2"

        >

          <strong>Sensor fault:</strong> {{ live.sensorFault }}

        </p>

        <p class="text-4xl font-bold text-white tabular-nums">

          {{ live.temp != null ? Number(live.temp).toFixed(1) : '—' }}

          <span class="text-lg text-zinc-500 font-normal">°C</span>

        </p>

        <p v-if="live.pidTarget != null" class="text-sm text-zinc-500 tabular-nums">

          Target {{ live.pidTarget }}°C

          <span v-if="live.pidActive && tempError != null" class="text-zinc-400">

            · {{ tempError > 0 ? '+' : '' }}{{ tempError.toFixed(1) }}°C to go

          </span>

        </p>

        <p class="text-xs text-zinc-600">

          Heater {{ live.heaterPwm }}% · {{ heaterStatus }}

          <span v-if="sessionActive"> · Fan {{ live.fanPwm }}%</span>

        </p>

      </section>



      <section class="rounded-2xl border border-violet-500/25 bg-violet-500/5 p-5 space-y-4">

        <h2 class="text-sm font-semibold text-violet-300 uppercase tracking-wider">PID gains</h2>

        <p class="text-xs text-zinc-500">

          Live on the bench server until restart. Values in

          <code class="bg-black/30 px-1 rounded">config.py</code>

          are only the startup default.

        </p>

        <div class="grid grid-cols-3 gap-3">

          <label class="block text-xs text-zinc-500">

            Kp

            <input

              v-model.number="pidKpInput"

              type="number"

              min="0"

              max="50"

              step="0.1"

              class="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-2 py-2 text-white tabular-nums"

              :disabled="!isConnected"

            >

          </label>

          <label class="block text-xs text-zinc-500">

            Ki

            <input

              v-model.number="pidKiInput"

              type="number"

              min="0"

              max="5"

              step="0.01"

              class="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-2 py-2 text-white tabular-nums"

              :disabled="!isConnected"

            >

          </label>

          <label class="block text-xs text-zinc-500">

            Kd

            <input

              v-model.number="pidKdInput"

              type="number"

              min="0"

              max="20"

              step="0.1"

              class="mt-1 w-full rounded-lg bg-black/30 border border-white/10 px-2 py-2 text-white tabular-nums"

              :disabled="!isConnected"

            >

          </label>

        </div>

        <label class="flex items-center gap-2 text-xs text-zinc-500 cursor-pointer">

          <input v-model="resetPidIntegral" type="checkbox" class="rounded border-white/20" :disabled="!isConnected">

          Reset integral when applying (clears wind-up)

        </label>

        <div class="flex flex-wrap gap-3">

          <button

            type="button"

            class="px-4 py-2 rounded-xl text-sm font-medium bg-violet-600 hover:bg-violet-500 text-white disabled:opacity-40"

            :disabled="!isConnected"

            @click="setPidGains(pidKpInput, pidKiInput, pidKdInput, resetPidIntegral)"

          >

            Apply gains

          </button>

          <button

            type="button"

            class="px-4 py-2 rounded-xl text-sm border border-white/10 hover:bg-white/5 disabled:opacity-40"

            :disabled="!isConnected"

            @click="pidKpInput = pidDefaults.kp; pidKiInput = pidDefaults.ki; pidKdInput = pidDefaults.kd"

          >

            Reset to config defaults

          </button>

          <button

            type="button"

            class="px-4 py-2 rounded-xl text-sm border border-violet-500/30 text-violet-200 hover:bg-violet-500/10 disabled:opacity-40"

            :disabled="!isConnected"

            @click="getPidGains"

          >

            Refresh from Pi

          </button>

        </div>

        <p v-if="live.pidKp != null" class="text-[10px] text-zinc-600 tabular-nums">

          Active on Pi: Kp {{ live.pidKp }} · Ki {{ live.pidKi }} · Kd {{ live.pidKd }}

        </p>

      </section>



      <section class="rounded-2xl border border-orange-500/25 bg-orange-500/5 p-5 space-y-4">

        <h2 class="text-sm font-semibold text-orange-300 uppercase tracking-wider">Heater</h2>

        <p class="text-xs text-zinc-500">

          One action: full relay power until within {{ 15 }}°C of target, then PID takes over.

          No manual on/off or pulse controls.

        </p>

        <label class="block text-xs text-zinc-500">

          Target temperature (°C)

          <input

            v-model.number="targetInput"

            type="number"

            min="20"

            max="245"

            step="1"

            class="mt-2 w-full rounded-lg bg-black/30 border border-white/10 px-3 py-2.5 text-white text-lg tabular-nums"

            :disabled="!isConnected"

          >

        </label>

        <div class="flex flex-wrap gap-3">

          <button

            type="button"

            class="flex-1 min-w-[140px] px-4 py-3 rounded-xl text-sm font-semibold bg-orange-600 hover:bg-orange-500 text-white disabled:opacity-40"

            :disabled="!isConnected || live.pidActive"

            @click="heatToTarget(targetInput)"

          >

            Heat to target

          </button>

          <button

            type="button"

            class="px-4 py-3 rounded-xl text-sm font-medium border border-white/10 hover:bg-white/5 disabled:opacity-40"

            :disabled="!isConnected || !live.pidActive"

            @click="stopHeating"

          >

            Stop heating

          </button>

          <button

            type="button"

            class="px-4 py-3 rounded-xl text-sm font-bold bg-red-600 hover:bg-red-500 text-white disabled:opacity-40"

            :disabled="!isConnected"

            @click="emergencyStop"

          >

            E-STOP

          </button>

        </div>

        <button

          v-if="live.pidActive"

          type="button"

          class="text-xs text-orange-300/80 hover:text-orange-200 underline-offset-2 hover:underline"

          @click="setTarget(targetInput)"

        >

          Apply new target while heating

        </button>

      </section>



      <section class="rounded-2xl border border-white/[0.06] bg-[#1a1714] p-5 space-y-4">

        <h2 class="text-sm font-semibold text-zinc-300 uppercase tracking-wider">Fan</h2>

        <p class="text-xs text-zinc-500 mb-2">

          Start a session for fan control (heating starts its own session automatically).

        </p>

        <div class="flex flex-wrap gap-3 mb-4">

          <button

            type="button"

            class="px-3 py-2 rounded-lg text-xs font-medium bg-zinc-700 hover:bg-zinc-600 disabled:opacity-40"

            :disabled="!isConnected || sessionActive"

            @click="startSession"

          >

            Start session

          </button>

          <button

            type="button"

            class="px-3 py-2 rounded-lg text-xs border border-white/10 hover:bg-white/5 disabled:opacity-40"

            :disabled="!isConnected || !sessionActive"

            @click="stopSession"

          >

            End session

          </button>

        </div>

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

            Apply fan

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



      <p v-if="lastResult?.note" class="text-xs text-center text-zinc-600">

        {{ lastResult.note }}

      </p>

    </main>

  </div>

</template>



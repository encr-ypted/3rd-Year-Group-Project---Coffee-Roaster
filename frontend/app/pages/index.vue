<script setup>
import { useCoffeeRoaster } from '~/composable/useCoffeeRoaster'

const {
  connect,
  loadProfiles,
  isConnected,
  liveData,
  roastDataPoints,
  roastPlan,
  setRoastPlanFromProfile,
  roastProfiles,
  profilesLoaded,
  startRoast,
  stopRoast,
  resumeRoast,
  finishRoast,
  emergencyStop,
  toggleTestSpin,
  lastError,
} = useCoffeeRoaster()

const isDark = ref(true)
const selectedProfile = ref(null)

onMounted(() => {
  connect()
  loadProfiles()
  const saved = localStorage.getItem('roaster-theme')
  if (saved !== null) isDark.value = saved === 'dark'
})

watch(roastProfiles, (list) => {
  if (!list.length) return
  if (!selectedProfile.value) {
    selectedProfile.value = list.find((p) => p.id === 'medium') ?? list[0]
    return
  }
  const match = list.find((p) => p.id === selectedProfile.value.id)
  if (match) selectedProfile.value = match
})

watch(isDark, (v) => localStorage.setItem('roaster-theme', v ? 'dark' : 'light'))

const tempMin = 20
const tempMax = 230

const progressPercent = computed(() => {
  const t = liveData.value.temp
  if (t == null) return 0
  return Math.min(100, Math.max(0, ((t - tempMin) / (tempMax - tempMin)) * 100))
})

const stateDisplay = computed(() => {
  const d = isDark.value
  const states = {
    IDLE:     { label: 'Idle',        dot: d ? 'bg-zinc-500'  : 'bg-stone-400',  pill: d ? 'bg-zinc-800/60 text-zinc-300'  : 'bg-stone-100 text-stone-600' },
    PREHEAT:  { label: 'Preheating',  dot: 'bg-amber-500',   pill: d ? 'bg-amber-500/10 text-amber-400'  : 'bg-amber-50 text-amber-700',   pulse: true },
    ROASTING: { label: 'Roasting',    dot: 'bg-orange-500',  pill: d ? 'bg-orange-500/10 text-orange-400' : 'bg-orange-50 text-orange-700', pulse: true },
    COOLING:  { label: 'Cooling',     dot: 'bg-sky-500',     pill: d ? 'bg-sky-500/10 text-sky-400'      : 'bg-sky-50 text-sky-700',       pulse: true },
    ERROR:    { label: 'Error',       dot: 'bg-red-500',     pill: d ? 'bg-red-500/10 text-red-400'      : 'bg-red-50 text-red-700',       pulse: true },
  }
  return states[liveData.value.state] || states.IDLE
})

const rorSign = computed(() => liveData.value.ror >= 0 ? '+' : '')

const rorDisplay = computed(() => {
  const r = liveData.value.ror
  if (!Number.isFinite(r)) return '—'
  const abs = Math.abs(r)
  if (abs >= 100) return `${rorSign.value}${r.toFixed(0)}`
  return `${rorSign.value}${r.toFixed(1)}`
})

const rorValueClass = computed(() => {
  const abs = Math.abs(liveData.value.ror)
  if (abs >= 100) return 'text-base sm:text-lg'
  return 'text-lg sm:text-xl'
})
const isIdle = computed(() => liveData.value.state === 'IDLE')

watch(selectedProfile, (profile) => {
  if (isIdle.value) setRoastPlanFromProfile(profile)
}, { immediate: true })
const isRoasting = computed(() => ['PREHEAT', 'ROASTING'].includes(liveData.value.state))

const chartTargetTemp = computed(() => {
  if (liveData.value.targetTemp > 0) return liveData.value.targetTemp
  return roastPlan.value?.target ?? 0
})
const isCooling = computed(() => liveData.value.state === 'COOLING')
const canResume = computed(() => isCooling.value && liveData.value.canResume)

// Theme color map — keeps the template clean
const c = computed(() => isDark.value ? {
  page:       'coffee-dark-bg',
  header:     'border-b border-white/[0.04]',
  card:       'bg-[#1a1714] border-white/[0.05] hover:border-white/[0.08]',
  glowVia:    'via-[rgba(196,138,50,0.25)]',
  label:      'text-zinc-500',
  secTitle:   'text-zinc-300',
  secSub:     'text-zinc-600',
  value:      'text-white',
  unit:       'text-zinc-600',
  tempLg:     'text-white',
  tempSm:     'text-zinc-600',
  rorPos:     'text-emerald-400',
  rorNeg:     'text-sky-400',
  icon:       'bg-[rgba(212,162,78,0.08)] border border-[rgba(212,162,78,0.1)]',
  iconHov:    'group-hover:bg-[rgba(212,162,78,0.15)]',
  iconClr:    'text-gold-400',
  track:      'bg-zinc-800/80',
  chartArea:  'bg-[#141210] border border-white/[0.04]',
  chartBox:   'bg-white/[0.03] border border-white/[0.04]',
  chartTxt:   'text-zinc-500',
  chartDim:   'text-zinc-700',
  profSel:    'border-gold-500/50 bg-gold-400/8 ring-1 ring-gold-400/15',
  profDef:    'border-white/[0.05] bg-white/[0.02] hover:bg-white/[0.04] hover:border-white/[0.08]',
  profLbl:    'text-zinc-600',
  profNSel:   'text-gold-300',
  profNDef:   'text-zinc-400',
  profTSel:   'text-gold-400',
  profTDef:   'text-zinc-600',
  profDesc:   'text-zinc-600',
  stopBtn:    'bg-gold-600 hover:bg-gold-500 shadow-lg shadow-gold-900/30',
  estopExtra: 'shadow-[0_0_30px_rgba(239,68,68,0.15)] hover:shadow-[0_0_40px_rgba(239,68,68,0.25)] border border-red-500/30',
  estopSub:   'text-zinc-600',
  divider:    'border-white/[0.04]',
  ringOff:    'focus-visible:ring-offset-[#1a1714]',
  toggleBg:   'bg-white/[0.06] hover:bg-white/10 text-amber-300',
  logoBg:     'bg-gold-400/10 border border-gold-400/10',
  logoClr:    'text-gold-400',
} : {
  page:       'coffee-light-bg',
  header:     'bg-gradient-to-r from-[#1e1408] to-[#3b2f1e] shadow-lg shadow-stone-900/10',
  card:       'bg-white shadow-[0_1px_3px_rgba(0,0,0,0.04),0_8px_24px_rgba(120,90,50,0.06)] hover:shadow-[0_1px_3px_rgba(0,0,0,0.04),0_12px_32px_rgba(120,90,50,0.10)]',
  glowVia:    'via-[rgba(196,138,50,0.12)]',
  label:      'text-stone-400',
  secTitle:   'text-stone-700',
  secSub:     'text-stone-400',
  value:      'text-stone-900',
  unit:       'text-stone-300',
  tempLg:     'text-stone-800',
  tempSm:     'text-stone-400',
  rorPos:     'text-emerald-700',
  rorNeg:     'text-sky-700',
  icon:       'bg-amber-500/10',
  iconHov:    'group-hover:bg-amber-500/15',
  iconClr:    'text-amber-600',
  track:      'bg-stone-200',
  chartArea:  'bg-[#faf6f1] border border-dashed border-stone-200/80',
  chartBox:   'bg-stone-200/50',
  chartTxt:   'text-stone-400',
  chartDim:   'text-stone-300',
  profSel:    'border-amber-500 bg-amber-50/80 ring-1 ring-amber-400/30',
  profDef:    'border-stone-200/80 bg-white hover:border-stone-300 hover:bg-stone-50/50',
  profLbl:    'text-stone-400',
  profNSel:   'text-amber-800',
  profNDef:   'text-stone-700',
  profTSel:   'text-amber-600',
  profTDef:   'text-stone-400',
  profDesc:   'text-stone-400',
  stopBtn:    'bg-amber-600 hover:bg-amber-700 shadow-lg shadow-amber-900/20',
  estopExtra: 'shadow-xl shadow-red-500/20 border-2 border-red-700',
  estopSub:   'text-stone-400',
  divider:    'border-stone-100',
  ringOff:    'focus-visible:ring-offset-white',
  toggleBg:   'bg-white/10 hover:bg-white/20 text-amber-300',
  logoBg:     'bg-amber-700/30',
  logoClr:    'text-amber-300',
})
</script>

<template>
  <div :class="c.page" class="min-h-screen w-full max-w-full overflow-x-clip transition-colors duration-500">

    <!-- Amber accent line -->
    <div class="h-[3px] bg-gradient-to-r from-gold-700 via-gold-400 to-gold-700" />

    <!-- ============================== HEADER ============================== -->
    <header :class="c.header" class="transition-colors duration-500">
      <div class="max-w-[1440px] mx-auto px-5 sm:px-8 lg:px-10 py-5 flex items-center justify-between gap-3 min-w-0">
        <div class="flex items-center gap-3 sm:gap-4 min-w-0 shrink">
          <div class="w-11 h-11 rounded-2xl flex items-center justify-center" :class="c.logoBg">
            <Icon name="lucide:coffee" class="w-5 h-5" :class="c.logoClr" />
          </div>
          <div>
            <h1 class="text-lg font-extrabold text-white tracking-tight">Smart Roaster</h1>
            <p class="text-[10px] text-zinc-400 tracking-[0.2em] uppercase font-semibold mt-0.5">
              Roast Monitor
            </p>
          </div>
        </div>

        <div class="flex items-center gap-2 sm:gap-3 shrink-0">
          <NuxtLink
            to="/hardware-test"
            class="hidden sm:inline-flex text-[11px] font-semibold px-3 py-2 rounded-xl border transition-colors"
            :class="isDark ? 'border-white/10 text-zinc-400 hover:text-gold-400' : 'border-stone-200 text-stone-500 hover:text-amber-700'"
          >
            HW Test
          </NuxtLink>
          <button
            :class="c.toggleBg"
            class="w-9 h-9 rounded-xl flex items-center justify-center transition-colors"
            @click="isDark = !isDark"
            :title="isDark ? 'Switch to light' : 'Switch to dark'"
          >
            <Icon :name="isDark ? 'lucide:sun' : 'lucide:moon'" class="w-4 h-4" />
          </button>

          <div
            class="flex items-center gap-2.5 px-4 py-2 rounded-full text-[11px] font-bold tracking-wide uppercase"
            :class="isConnected
              ? 'bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/15'
              : 'bg-red-500/10 text-red-400 ring-1 ring-red-500/15'"
          >
            <span
              class="w-1.5 h-1.5 rounded-full"
              :class="isConnected ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'"
            />
            {{ isConnected ? 'Online' : 'Offline' }}
          </div>
        </div>
      </div>
    </header>

    <!-- ============================== MAIN — SIDEBAR LAYOUT ============================== -->
    <main class="relative max-w-[1440px] mx-auto px-5 sm:px-8 lg:px-10 py-8 overflow-x-clip">
      <p
        v-if="lastError"
        class="relative mb-5 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3"
      >
        {{ lastError }}
      </p>

      <!-- Ambient glow (dark only) — clipped to main width -->
      <div
        v-if="isDark"
        class="pointer-events-none absolute inset-x-0 top-0 h-[400px] overflow-hidden"
        aria-hidden="true"
      >
        <div class="absolute left-1/2 top-0 -translate-x-1/2 w-full max-w-3xl h-full bg-gold-500/[0.02] rounded-full blur-3xl" />
      </div>

      <div class="relative xl:grid xl:grid-cols-[minmax(0,320px)_minmax(0,1fr)] xl:gap-7 space-y-6 xl:space-y-0 min-w-0">

        <!-- ==================== LEFT SIDEBAR ==================== -->
        <aside class="xl:sticky xl:top-8 xl:self-start space-y-4 min-w-0">

          <!-- Hero Temperature Card -->
          <div class="card-base" :class="c.card">
            <div class="glow-line" :class="c.glowVia" />
            <div class="flex items-center justify-between mb-2">
              <span class="lbl" :class="c.label">Bean temp</span>
              <div class="icon-wrap" :class="[c.icon, c.iconHov]">
                <Icon name="lucide:thermometer" class="w-4 h-4" :class="c.iconClr" />
              </div>
            </div>

            <p class="text-[2.75rem] sm:text-[3.25rem] leading-none font-extrabold tracking-tighter tabular-nums" :class="c.value">
              {{ liveData.temp != null ? liveData.temp.toFixed(1) : '—' }}<span class="text-lg font-semibold ml-1" :class="c.unit">°C</span>
            </p>
            <p
              v-if="liveData.tempAir != null"
              class="mt-1 text-xs tabular-nums"
              :class="c.secSub"
            >
              Chamber {{ liveData.tempAir.toFixed(1) }}°C
              <span class="text-zinc-600"> · heater control</span>
            </p>
            <p
              v-if="liveData.sensorFaultBean || liveData.sensorFaultAir"
              class="mt-2 text-xs font-medium text-amber-400/90 leading-snug"
            >
              <span v-if="liveData.sensorFaultBean">Bean: {{ liveData.sensorFaultBean }}</span>
              <span v-if="liveData.sensorFaultBean && liveData.sensorFaultAir"> · </span>
              <span v-if="liveData.sensorFaultAir">Air: {{ liveData.sensorFaultAir }}</span>
            </p>

            <!-- Integrated progress gauge -->
            <div class="mt-5">
              <div class="relative h-2.5 rounded-full overflow-hidden" :class="c.track">
                <div class="absolute inset-0 rounded-full bg-gradient-to-r from-emerald-500 via-gold-400 via-[60%] to-red-500 opacity-90" />
                <div
                  class="absolute top-0 right-0 h-full transition-all duration-700 ease-out"
                  :class="c.track"
                  :style="{ width: `${100 - progressPercent}%` }"
                />
              </div>
              <div class="flex items-center justify-between mt-2">
                <span class="tick" :class="c.tempSm">{{ tempMin }}°</span>
                <span class="text-[11px] font-extrabold tabular-nums" :class="c.tempLg">{{ progressPercent.toFixed(0) }}%</span>
                <span class="tick" :class="c.tempSm">{{ tempMax }}°</span>
              </div>
            </div>
          </div>

          <!-- Mini Stats Row -->
          <div class="grid grid-cols-3 gap-2 sm:gap-3 min-w-0">
            <!-- Target -->
            <div
              class="card-base !p-3 sm:!p-4 flex flex-col items-center justify-center text-center min-h-[5.25rem] min-w-0"
              :class="c.card"
            >
              <span class="lbl text-[8px] shrink-0" :class="c.label">
                {{ isRoasting ? 'Setpoint' : 'Target' }}
              </span>
              <div class="mt-1.5 flex flex-col items-center leading-none min-w-0 w-full">
                <span class="text-lg sm:text-xl font-extrabold tabular-nums" :class="c.value">
                  {{ (isRoasting ? liveData.setpointTemp : liveData.targetTemp).toFixed(0) }}
                </span>
                <span class="text-[9px] font-semibold mt-0.5" :class="c.unit">
                  °C<span v-if="isRoasting && liveData.targetTemp > liveData.setpointTemp">
                    → {{ liveData.targetTemp.toFixed(0) }}
                  </span>
                </span>
              </div>
            </div>

            <!-- RoR -->
            <div
              class="card-base !p-3 sm:!p-4 flex flex-col items-center justify-center text-center min-h-[5.25rem] min-w-0"
              :class="c.card"
            >
              <span class="lbl text-[8px] shrink-0" :class="c.label">RoR</span>
              <div class="mt-1.5 flex flex-col items-center leading-none min-w-0 w-full max-w-full">
                <span
                  class="font-extrabold tabular-nums max-w-full truncate px-0.5"
                  :class="[rorValueClass, liveData.ror >= 0 ? c.rorPos : c.rorNeg]"
                >
                  {{ rorDisplay }}
                </span>
                <span class="text-[9px] font-semibold mt-0.5 shrink-0" :class="c.unit">°/min</span>
              </div>
            </div>

            <!-- State -->
            <div
              class="card-base !p-3 sm:!p-4 flex flex-col items-center justify-center text-center min-h-[5.25rem] min-w-0 w-full"
              :class="c.card"
            >
              <span class="lbl text-[8px] shrink-0" :class="c.label">State</span>
              <span
                class="mt-1.5 inline-flex w-full max-w-full items-center justify-center gap-1 px-1.5 py-1 rounded-full text-[8px] sm:text-[9px] font-bold leading-tight"
                :class="stateDisplay.pill"
              >
                <span
                  class="w-1.5 h-1.5 rounded-full shrink-0"
                  :class="[stateDisplay.dot, stateDisplay.pulse && 'animate-pulse']"
                />
                <span class="truncate">{{ stateDisplay.label }}</span>
              </span>
            </div>
          </div>

          <!-- Sidebar Controls (visible on xl only, hidden on mobile where it appears below chart) -->
          <div class="hidden xl:block card-base" :class="c.card">
            <div class="glow-line" :class="c.glowVia" />
            <div class="flex items-center gap-3 mb-5">
              <div class="icon-wrap" :class="c.icon">
                <Icon name="lucide:sliders-horizontal" class="w-4 h-4" :class="c.iconClr" />
              </div>
              <h3 class="text-xs font-bold uppercase tracking-widest" :class="c.secTitle">Controls</h3>
            </div>

            <!-- Profile Selector -->
            <div class="mb-5">
              <label class="text-[9px] font-bold uppercase tracking-[0.15em] mb-2 block" :class="c.profLbl">
                Roast Profile
              </label>
              <p v-if="!profilesLoaded" class="text-[10px]" :class="c.profLbl">Loading profiles from Pi…</p>
              <div v-else class="grid grid-cols-2 gap-2">
                <button
                  v-for="profile in roastProfiles"
                  :key="profile.id"
                  :disabled="!isIdle || !selectedProfile"
                  class="prof-btn"
                  :class="selectedProfile?.id === profile.id ? c.profSel : c.profDef"
                  @click="isIdle && (selectedProfile = profile)"
                >
                  <div class="flex items-center gap-1.5 mb-0.5">
                    <span class="w-2 h-2 rounded-full shrink-0" :class="profile.dot" />
                    <span
                      class="text-[11px] font-bold truncate"
                      :class="selectedProfile?.id === profile.id ? c.profNSel : c.profNDef"
                    >{{ profile.name }}</span>
                  </div>
                  <span
                    class="text-[10px] font-bold tabular-nums"
                    :class="selectedProfile?.id === profile.id ? c.profTSel : c.profTDef"
                  >{{ profile.temp }}°C · σ {{ profile.rampMid }}m</span>
                </button>
              </div>
            </div>

            <!-- Buttons -->
            <div class="space-y-2">
              <button
                v-if="isIdle"
                :disabled="!isConnected"
                :class="[
                  c.ringOff,
                  liveData.testSpin
                    ? 'bg-sky-700 hover:bg-sky-600 ring-2 ring-sky-400/40'
                    : 'bg-sky-600 hover:bg-sky-500 shadow-sky-900/30',
                ]"
                class="ctrl-btn text-white shadow-lg disabled:opacity-30 disabled:cursor-not-allowed disabled:shadow-none
                       focus-visible:ring-sky-500"
                @click="toggleTestSpin()"
              >
                <Icon name="lucide:wind" class="w-4 h-4" />
                {{ liveData.testSpin ? 'Stop test spin' : 'Test spin' }}
              </button>
              <p v-if="isIdle" class="text-[9px] text-center -mt-1" :class="c.profLbl">
                Fan ramps on — check beans are tumbling before you roast
              </p>

              <button
                v-if="!isCooling"
                :disabled="!isIdle || !isConnected || !selectedProfile"
                :class="c.ringOff"
                class="ctrl-btn bg-emerald-600 hover:bg-emerald-500
                       focus-visible:ring-emerald-500 text-white shadow-lg shadow-emerald-900/30
                       disabled:opacity-30 disabled:cursor-not-allowed disabled:shadow-none"
                @click="startRoast(selectedProfile.id)"
              >
                <Icon name="lucide:play" class="w-4 h-4" />
                Start Roast
              </button>

              <button
                v-if="isRoasting"
                :disabled="!isConnected"
                :class="[c.stopBtn, c.ringOff]"
                class="ctrl-btn text-white
                       disabled:opacity-30 disabled:cursor-not-allowed disabled:shadow-none
                       focus-visible:ring-amber-500"
                @click="stopRoast()"
              >
                <Icon name="lucide:square" class="w-4 h-4" />
                Stop &amp; Cool
              </button>

              <template v-if="canResume">
                <button
                  :disabled="!isConnected"
                  :class="c.ringOff"
                  class="ctrl-btn bg-sky-600 hover:bg-sky-500 text-white
                         focus-visible:ring-sky-500 disabled:opacity-30"
                  @click="resumeRoast()"
                >
                  <Icon name="lucide:play" class="w-4 h-4" />
                  Resume roast
                </button>
                <button
                  :disabled="!isConnected"
                  :class="c.ringOff"
                  class="ctrl-btn bg-amber-700 hover:bg-amber-600 text-white
                         focus-visible:ring-amber-500 disabled:opacity-30"
                  @click="finishRoast()"
                >
                  <Icon name="lucide:save" class="w-4 h-4" />
                  Finish now
                </button>
                <p class="text-[9px] text-center" :class="c.profLbl">
                  Finish now saves the log; fan stays on until cool-down completes
                </p>
              </template>
            </div>

            <div class="mt-4 pt-4 space-y-3" :class="'border-t ' + c.divider">
              <button
                :class="c.estopExtra"
                class="w-full py-3.5 rounded-2xl bg-red-600 hover:bg-red-500 active:scale-[0.98]
                       text-white font-black text-xs uppercase tracking-[0.2em]
                       transition-all duration-200 flex items-center justify-center gap-2
                       focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
                @click="emergencyStop()"
              >
                <Icon name="lucide:shield-alert" class="w-5 h-5" />
                Emergency Stop
              </button>
              <p class="text-[9px] text-center tracking-wider uppercase" :class="c.estopSub">
                Heater off · fan on max
              </p>
            </div>
          </div>
        </aside>

        <!-- ==================== RIGHT MAIN CONTENT ==================== -->
        <div class="space-y-5 min-w-0">

          <!-- Chart -->
          <div class="card-base" :class="c.card">
            <div class="glow-line" :class="c.glowVia" />
            <div class="flex items-center gap-3 mb-5">
              <div class="icon-wrap" :class="c.icon">
                <Icon name="lucide:line-chart" class="w-4 h-4" :class="c.iconClr" />
              </div>
              <div>
                <h3 class="text-xs font-bold uppercase tracking-widest" :class="c.secTitle">Roast Profile</h3>
                <p class="text-[10px] mt-0.5" :class="c.secSub">
                  Planned curve, bean &amp; chamber air, RoR
                </p>
              </div>
            </div>

            <div class="rounded-2xl overflow-hidden" :class="c.chartArea">
              <ClientOnly>
                <RoastChart
                  :points="roastDataPoints"
                  :target="chartTargetTemp"
                  :plan="roastPlan"
                  :roasting="isRoasting"
                  :dark="isDark"
                />
                <template #fallback>
                  <div
                    class="flex items-center justify-center text-xs text-zinc-500"
                    style="min-height: 440px"
                  >
                    Loading chart…
                  </div>
                </template>
              </ClientOnly>
            </div>
          </div>

          <!-- Horizontal Controls Bar (mobile/tablet only — hidden on xl where sidebar has controls) -->
          <div class="xl:hidden card-base" :class="c.card">
            <div class="glow-line" :class="c.glowVia" />

            <div class="sm:grid sm:grid-cols-[minmax(0,1fr)_minmax(0,auto)] sm:gap-6 min-w-0">
              <!-- Profile Selector -->
              <div>
                <label class="text-[9px] font-bold uppercase tracking-[0.15em] mb-2.5 block" :class="c.profLbl">
                  Roast Profile
                </label>
                <p v-if="!profilesLoaded" class="text-[10px] mb-4 sm:mb-0" :class="c.profLbl">Loading profiles from Pi…</p>
                <div v-else class="grid grid-cols-2 gap-2 mb-4 sm:mb-0">
                  <button
                    v-for="profile in roastProfiles"
                    :key="'m-' + profile.id"
                    :disabled="!isIdle || !selectedProfile"
                    class="prof-btn"
                    :class="selectedProfile?.id === profile.id ? c.profSel : c.profDef"
                    @click="isIdle && (selectedProfile = profile)"
                  >
                    <div class="flex items-center gap-1.5 mb-0.5">
                      <span class="w-2 h-2 rounded-full shrink-0" :class="profile.dot" />
                      <span
                        class="text-[11px] font-bold truncate"
                        :class="selectedProfile?.id === profile.id ? c.profNSel : c.profNDef"
                      >{{ profile.name }}</span>
                    </div>
                    <span
                      class="text-[10px] font-bold tabular-nums"
                      :class="selectedProfile?.id === profile.id ? c.profTSel : c.profTDef"
                    >{{ profile.temp }}°C · σ {{ profile.rampMid }}m</span>
                  </button>
                </div>
              </div>

              <!-- Buttons stack -->
              <div class="flex flex-col gap-2 min-w-0 sm:w-auto">
                <button
                  v-if="isIdle"
                  :disabled="!isConnected"
                  :class="[
                    c.ringOff,
                    liveData.testSpin
                      ? 'bg-sky-700 hover:bg-sky-600 ring-2 ring-sky-400/40'
                      : 'bg-sky-600 hover:bg-sky-500 shadow-sky-900/30',
                  ]"
                  class="ctrl-btn text-white shadow-lg disabled:opacity-30 disabled:cursor-not-allowed disabled:shadow-none
                         focus-visible:ring-sky-500"
                  @click="toggleTestSpin()"
                >
                  <Icon name="lucide:wind" class="w-4 h-4" />
                  {{ liveData.testSpin ? 'Stop test spin' : 'Test spin' }}
                </button>
                <p v-if="isIdle" class="text-[9px] text-center sm:hidden" :class="c.profLbl">
                  Fan ramps on — check bean tumble before roasting
                </p>

                <button
                  v-if="!isCooling"
                  :disabled="!isIdle || !isConnected || !selectedProfile"
                  :class="c.ringOff"
                  class="ctrl-btn bg-emerald-600 hover:bg-emerald-500
                         focus-visible:ring-emerald-500 text-white shadow-lg shadow-emerald-900/30
                         disabled:opacity-30 disabled:cursor-not-allowed disabled:shadow-none"
                  @click="startRoast(selectedProfile.id)"
                >
                  <Icon name="lucide:play" class="w-4 h-4" />
                  Start Roast
                </button>

                <button
                  v-if="isRoasting"
                  :disabled="!isConnected"
                  :class="[c.stopBtn, c.ringOff]"
                  class="ctrl-btn text-white
                         disabled:opacity-30 disabled:cursor-not-allowed disabled:shadow-none
                         focus-visible:ring-amber-500"
                  @click="stopRoast()"
                >
                  <Icon name="lucide:square" class="w-4 h-4" />
                  Stop &amp; Cool
                </button>

                <template v-if="canResume">
                  <button
                    :disabled="!isConnected"
                    :class="c.ringOff"
                    class="ctrl-btn bg-sky-600 hover:bg-sky-500 text-white focus-visible:ring-sky-500 disabled:opacity-30"
                    @click="resumeRoast()"
                  >
                    <Icon name="lucide:play" class="w-4 h-4" />
                    Resume roast
                  </button>
                  <button
                    :disabled="!isConnected"
                    :class="c.ringOff"
                    class="ctrl-btn bg-amber-700 hover:bg-amber-600 text-white focus-visible:ring-amber-500 disabled:opacity-30"
                    @click="finishRoast()"
                  >
                    <Icon name="lucide:save" class="w-4 h-4" />
                    Finish now
                  </button>
                </template>
              </div>
            </div>

            <div class="mt-5 pt-4 space-y-3" :class="'border-t ' + c.divider">
              <button
                :class="c.estopExtra"
                class="w-full py-4 rounded-2xl bg-red-600 hover:bg-red-500 active:scale-[0.98]
                       text-white font-black text-sm uppercase tracking-[0.2em]
                       transition-all duration-200 flex items-center justify-center gap-2.5
                       focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400"
                @click="emergencyStop()"
              >
                <Icon name="lucide:shield-alert" class="w-5 h-5" />
                Emergency Stop
              </button>
              <p class="text-[9px] text-center tracking-wider uppercase" :class="c.estopSub">
                Heater off · fan on max
              </p>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
@reference "tailwindcss";

.card-base {
  @apply relative overflow-hidden rounded-2xl p-6 border transition-all duration-300;
}

.glow-line {
  @apply absolute top-0 left-6 right-6 h-px bg-gradient-to-r from-transparent to-transparent;
}

.lbl {
  @apply text-[10px] font-bold uppercase tracking-[0.12em];
}

.icon-wrap {
  @apply w-9 h-9 rounded-xl flex items-center justify-center transition-colors duration-200;
}

.val {
  @apply text-[2.5rem] leading-none font-extrabold tracking-tight tabular-nums;
}

.val-unit {
  @apply text-sm font-semibold ml-1;
}

.tick {
  @apply text-[10px] font-semibold tabular-nums;
}

.ctrl-btn {
  @apply w-full py-3 px-4 rounded-xl font-bold text-xs uppercase tracking-widest
         flex items-center justify-center gap-2
         transition-all duration-200 active:scale-[0.97]
         focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2;
}

.prof-btn {
  @apply min-w-0 rounded-xl border px-3 py-2.5 text-left cursor-pointer
         transition-all duration-150
         disabled:opacity-40 disabled:cursor-not-allowed;
}
</style>

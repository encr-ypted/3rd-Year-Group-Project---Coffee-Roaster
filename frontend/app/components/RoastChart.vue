<script setup>
import {
  Chart,
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  Legend,
  Tooltip,
  Filler,
} from 'chart.js'
import { buildPlannedTrajectory, planFromTelemetry } from '~/utils/roastRamp'
import { emaSmooth } from '~/utils/smoothSeries'

/** Display smoothing — raw telemetry is unchanged in roastDataPoints. */
const SMOOTH_TEMP_ALPHA = 0.38

Chart.register(
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  Legend,
  Tooltip,
  Filler,
)

const props = defineProps({
  points: {
    type: Array,
    default: () => [],
  },
  target: {
    type: Number,
    default: 0,
  },
  plan: {
    type: Object,
    default: null,
  },
  roasting: {
    type: Boolean,
    default: false,
  },
  dark: {
    type: Boolean,
    default: true,
  },
})

const canvasRef = ref(null)
let chart = null

const hasPlan = computed(() => props.plan?.target > 0 && props.plan?.startTemp != null)
const hasLive = computed(() => props.points.length > 0)
const showChart = computed(() => hasPlan.value || hasLive.value)

const chartPlan = computed(() => {
  if (!hasPlan.value) return null
  if (props.roasting && props.plan?.locked) {
    return planFromTelemetry(props.plan, props.points)
  }
  return props.plan
})

const plannedStepSec = computed(() => (props.roasting ? 0.5 : 20))

const maxTimeSec = computed(() => {
  let max = 120
  if (hasLive.value) {
    max = Math.max(max, ...props.points.map((p) => p.timestamp ?? 0))
  }
  if (chartPlan.value) {
    const planned = buildPlannedTrajectory(chartPlan.value, plannedStepSec.value)
    if (planned.length) {
      max = Math.max(max, planned[planned.length - 1].x)
    }
  }
  return max + 30
})

function chartColors() {
  if (props.dark) {
    return {
      grid: 'rgba(255,255,255,0.06)',
      tick: '#a1a1aa',
      temp: '#f97316',
      tempFill: 'rgba(249,115,22,0.1)',
      planned: 'rgba(212,162,78,0.85)',
      profileMax: 'rgba(161,161,170,0.45)',
    }
  }
  return {
    grid: 'rgba(0,0,0,0.06)',
    tick: '#78716c',
    temp: '#d97706',
    tempFill: 'rgba(217,119,6,0.12)',
    planned: 'rgba(180,83,9,0.75)',
    profileMax: 'rgba(120,113,108,0.5)',
  }
}

function xyPoints(points, yKey) {
  return points
    .filter((p) => p[yKey] != null && Number.isFinite(p[yKey]))
    .map((p) => ({ x: p.timestamp ?? 0, y: p[yKey] }))
}

function smoothLive(series, alpha) {
  if (series.length < 2) return series
  return emaSmooth(series, alpha)
}

function buildDatasets(colors) {
  const datasets = []

  if (chartPlan.value) {
    datasets.push({
      label: 'Planned setpoint',
      data: buildPlannedTrajectory(chartPlan.value, plannedStepSec.value),
      borderColor: colors.planned,
      borderDash: [8, 4],
      borderWidth: 2,
      pointRadius: 0,
      fill: false,
      yAxisID: 'y',
      order: 4,
    })
  }

  if (props.target > 0 && maxTimeSec.value > 0) {
    datasets.push({
      label: 'Profile max',
      data: [
        { x: 0, y: props.target },
        { x: maxTimeSec.value, y: props.target },
      ],
      borderColor: colors.profileMax,
      borderDash: [12, 8],
      borderWidth: 1,
      pointRadius: 0,
      fill: false,
      yAxisID: 'y',
      order: 5,
    })
  }

  const tempSeries = smoothLive(xyPoints(props.points, 'temp'), SMOOTH_TEMP_ALPHA)
  if (tempSeries.length) {
    datasets.push({
      label: 'Temperature',
      data: tempSeries,
      borderColor: colors.temp,
      backgroundColor: colors.tempFill,
      fill: true,
      tension: 0.25,
      pointRadius: 0,
      borderWidth: 2.5,
      yAxisID: 'y',
      order: 1,
    })
  }

  const setpoint = xyPoints(props.points, 'setpointTemp')
  if (setpoint.length && props.roasting) {
    datasets.push({
      label: 'Live setpoint',
      data: setpoint,
      borderColor: colors.planned,
      borderDash: [3, 2],
      borderWidth: 1,
      pointRadius: 0,
      fill: false,
      yAxisID: 'y',
      order: 3,
    })
  }

  return datasets
}

function buildOptions(colors) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    parsing: false,
    interaction: { mode: 'nearest', intersect: false, axis: 'x' },
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          color: colors.tick,
          boxWidth: 10,
          padding: 14,
          font: { size: 10 },
          usePointStyle: true,
        },
      },
      tooltip: {
        callbacks: {
          title: (items) => {
            const x = items[0]?.parsed?.x ?? 0
            const m = Math.floor(x / 60)
            const s = Math.round(x % 60)
            return `${m}:${String(s).padStart(2, '0')}`
          },
          label: (ctx) => {
            const y = ctx.parsed.y
            return `${ctx.dataset.label}: ${y?.toFixed?.(1) ?? y}°C`
          },
        },
      },
    },
    scales: {
      x: {
        type: 'linear',
        min: 0,
        max: maxTimeSec.value,
        title: { display: true, text: 'Roast time', color: colors.tick, font: { size: 10 } },
        ticks: {
          color: colors.tick,
          maxTicksLimit: 10,
          callback: (v) => {
            const m = Math.floor(v / 60)
            const s = Math.round(v % 60)
            return s === 0 ? `${m}m` : `${m}:${String(s).padStart(2, '0')}`
          },
        },
        grid: { color: colors.grid },
      },
      y: {
        position: 'left',
        title: { display: true, text: 'Temperature °C', color: colors.tick, font: { size: 10 } },
        ticks: { color: colors.tick },
        grid: { color: colors.grid },
      },
    },
  }
}

function syncChart() {
  if (!canvasRef.value || !showChart.value) return

  const colors = chartColors()
  const datasets = buildDatasets(colors)

  if (!chart) {
    chart = new Chart(canvasRef.value, {
      type: 'line',
      data: { datasets },
      options: buildOptions(colors),
    })
    return
  }

  chart.data.datasets = datasets
  chart.options = buildOptions(colors)
  chart.update('none')
}

watch(
  () => [props.points, props.target, props.plan, props.roasting, props.dark, chartPlan.value],
  () => syncChart(),
  { deep: true },
)

watch(showChart, (visible) => {
  if (visible) nextTick(() => syncChart())
})

onMounted(() => {
  nextTick(() => syncChart())
})

onUnmounted(() => {
  chart?.destroy()
  chart = null
})
</script>

<template>
  <div
    id="roast-chart-container"
    class="relative w-full max-w-full min-w-0 rounded-2xl overflow-hidden"
    style="min-height: min(440px, 55vh); height: min(440px, 55vh)"
  >
    <canvas ref="canvasRef" class="absolute inset-0 w-full h-full" />
    <div
      v-if="!showChart"
      class="absolute inset-0 flex flex-col items-center justify-center pointer-events-none px-6 text-center"
    >
      <p class="text-xs font-semibold text-zinc-500">No profile selected</p>
      <p class="text-[10px] mt-1 text-zinc-600">Choose a profile to preview the setpoint ramp from current bean temp</p>
    </div>
    <p
      v-else-if="!roasting && hasPlan"
      class="absolute top-2 right-3 text-[10px] text-zinc-500 pointer-events-none"
    >
      Preview — start roast for live temperature trace
    </p>
  </div>
</template>

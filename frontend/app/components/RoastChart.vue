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
import { buildPlannedTrajectory } from '~/utils/roastRamp'

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

const maxTimeSec = computed(() => {
  let max = 120
  if (hasLive.value) {
    max = Math.max(max, ...props.points.map((p) => p.timestamp ?? 0))
  }
  if (hasPlan.value) {
    const planned = buildPlannedTrajectory(props.plan, 20)
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
      bean: '#f97316',
      beanFill: 'rgba(249,115,22,0.1)',
      air: '#38bdf8',
      planned: 'rgba(212,162,78,0.85)',
      profileMax: 'rgba(161,161,170,0.45)',
      ror: '#a78bfa',
    }
  }
  return {
    grid: 'rgba(0,0,0,0.06)',
    tick: '#78716c',
    bean: '#d97706',
    beanFill: 'rgba(217,119,6,0.12)',
    air: '#0284c7',
    planned: 'rgba(180,83,9,0.75)',
    profileMax: 'rgba(120,113,108,0.5)',
    ror: '#7c3aed',
  }
}

function xyPoints(points, yKey) {
  return points
    .filter((p) => p[yKey] != null && Number.isFinite(p[yKey]))
    .map((p) => ({ x: p.timestamp ?? 0, y: p[yKey] }))
}

function buildDatasets(colors) {
  const datasets = []

  if (hasPlan.value) {
    datasets.push({
      label: 'Planned profile',
      data: buildPlannedTrajectory(props.plan, 20),
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

  const bean = xyPoints(props.points, 'temp')
  if (bean.length) {
    datasets.push({
      label: 'Bean',
      data: bean,
      borderColor: colors.bean,
      backgroundColor: colors.beanFill,
      fill: true,
      tension: 0.25,
      pointRadius: 0,
      borderWidth: 2.5,
      yAxisID: 'y',
      order: 1,
    })
  }

  const air = xyPoints(props.points, 'tempAir')
  if (air.length) {
    datasets.push({
      label: 'Chamber (air)',
      data: air,
      borderColor: colors.air,
      tension: 0.25,
      pointRadius: 0,
      borderWidth: 2,
      yAxisID: 'y',
      order: 2,
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

  const ror = props.points
    .filter((p) => p.ror != null && Number.isFinite(p.ror))
    .map((p) => ({ x: p.timestamp ?? 0, y: p.ror }))
  if (ror.length) {
    datasets.push({
      label: 'RoR',
      data: ror,
      borderColor: colors.ror,
      pointRadius: 0,
      borderWidth: 1.5,
      tension: 0.25,
      yAxisID: 'y1',
      order: 0,
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
            const unit = ctx.dataset.yAxisID === 'y1' ? '°/min' : '°C'
            return `${ctx.dataset.label}: ${y?.toFixed?.(1) ?? y}${unit}`
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
      y1: {
        position: 'right',
        title: { display: true, text: 'RoR °/min', color: colors.tick, font: { size: 10 } },
        ticks: { color: colors.tick },
        grid: { drawOnChartArea: false },
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
  () => [props.points, props.target, props.plan, props.roasting, props.dark],
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
      <p class="text-[10px] mt-1 text-zinc-600">Choose a roast profile to preview the planned curve</p>
    </div>
    <p
      v-else-if="!roasting && hasPlan"
      class="absolute top-2 right-3 text-[10px] text-zinc-500 pointer-events-none"
    >
      Preview — start roast for live bean &amp; chamber traces
    </p>
  </div>
</template>

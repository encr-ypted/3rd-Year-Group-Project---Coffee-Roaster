<script setup>
import {
  Chart,
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Legend,
  Tooltip,
  Filler,
} from 'chart.js'

Chart.register(
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
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
  dark: {
    type: Boolean,
    default: true,
  },
})

const canvasRef = ref(null)
let chart = null

const hasData = computed(() => props.points.length > 0)

function chartColors() {
  if (props.dark) {
    return {
      grid: 'rgba(255,255,255,0.06)',
      tick: '#71717a',
      temp: '#f97316',
      tempFill: 'rgba(249,115,22,0.08)',
      target: 'rgba(212,162,78,0.7)',
      ror: '#38bdf8',
    }
  }
  return {
    grid: 'rgba(0,0,0,0.06)',
    tick: '#78716c',
    temp: '#d97706',
    tempFill: 'rgba(217,119,6,0.1)',
    target: 'rgba(180,83,9,0.6)',
    ror: '#0284c7',
  }
}

function buildDatasets(colors) {
  const temps = props.points.map((p) => p.temp)
  const targetLine =
    props.target > 0 ? props.points.map(() => props.target) : []

  const datasets = [
    {
      label: 'Bean °C',
      data: temps,
      borderColor: colors.temp,
      backgroundColor: colors.tempFill,
      fill: true,
      tension: 0.25,
      pointRadius: 0,
      borderWidth: 2,
      yAxisID: 'y',
    },
  ]

  if (targetLine.length) {
    datasets.push({
      label: 'Target',
      data: targetLine,
      borderColor: colors.target,
      borderDash: [6, 4],
      pointRadius: 0,
      borderWidth: 1.5,
      fill: false,
      yAxisID: 'y',
    })
  }

  datasets.push({
    label: 'RoR °/min',
    data: props.points.map((p) => p.ror ?? 0),
    borderColor: colors.ror,
    pointRadius: 0,
    borderWidth: 1.5,
    tension: 0.25,
    yAxisID: 'y1',
  })

  return datasets
}

function buildOptions(colors) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        labels: { color: colors.tick, boxWidth: 12, font: { size: 11 } },
      },
      tooltip: {
        callbacks: {
          title: (items) => {
            const t = items[0]?.label ?? items[0]?.parsed?.x ?? ''
            return `${t} s`
          },
        },
      },
    },
    scales: {
      x: {
        title: { display: true, text: 'Time (s)', color: colors.tick, font: { size: 10 } },
        ticks: { color: colors.tick, maxTicksLimit: 12 },
        grid: { color: colors.grid },
      },
      y: {
        position: 'left',
        title: { display: true, text: '°C', color: colors.tick, font: { size: 10 } },
        ticks: { color: colors.tick },
        grid: { color: colors.grid },
      },
      y1: {
        position: 'right',
        title: { display: true, text: '°/min', color: colors.tick, font: { size: 10 } },
        ticks: { color: colors.tick },
        grid: { drawOnChartArea: false },
      },
    },
  }
}

function syncChart() {
  if (!canvasRef.value) return

  const colors = chartColors()
  const labels = props.points.map((p) => p.timestamp ?? 0)
  const datasets = buildDatasets(colors)

  if (!chart) {
    chart = new Chart(canvasRef.value, {
      type: 'line',
      data: { labels, datasets },
      options: buildOptions(colors),
    })
    return
  }

  chart.data.labels = labels
  chart.data.datasets = datasets
  chart.options = buildOptions(colors)
  chart.update('none')
}

watch(
  () => [props.points, props.target, props.dark],
  () => syncChart(),
  { deep: true },
)

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
      v-if="!hasData"
      class="absolute inset-0 flex flex-col items-center justify-center pointer-events-none"
    >
      <p class="text-xs font-semibold text-zinc-500">No roast data yet</p>
      <p class="text-[10px] mt-1 text-zinc-600">Start a roast to plot temperature and RoR</p>
    </div>
  </div>
</template>

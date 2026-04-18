<template>
  <div class="flex flex-col gap-3">
    <div class="text-[10px] text-zinc-500 tracking-widest border-b border-dashed border-outline-variant/30 pb-2">
      OVERALL STATUS
    </div>

    <div v-if="error" class="text-error text-[10px] font-mono">{{ error }}</div>

    <!-- Big numbers row -->
    <div v-if="stats" class="grid grid-cols-3 gap-3">
      <div class="flex flex-col gap-1 items-center bg-surface-container-lowest py-3">
        <span class="text-2xl font-bold font-mono text-secondary">{{ stats.converted.toLocaleString() }}</span>
        <span class="text-[9px] text-zinc-500 tracking-widest uppercase">converted</span>
      </div>
      <div class="flex flex-col gap-1 items-center bg-surface-container-lowest py-3">
        <span class="text-2xl font-bold font-mono text-zinc-300">{{ stats.not_started.toLocaleString() }}</span>
        <span class="text-[9px] text-zinc-500 tracking-widest uppercase">remaining</span>
      </div>
      <div class="flex flex-col gap-1 items-center bg-surface-container-lowest py-3">
        <span class="text-2xl font-bold font-mono text-primary-container">{{ stats.human_review.toLocaleString() }}</span>
        <span class="text-[9px] text-zinc-500 tracking-widest uppercase">needs review</span>
      </div>
    </div>

    <!-- Overall progress bar -->
    <div v-if="stats && stats.total > 0" class="flex flex-col gap-1">
      <div class="h-3 w-full bg-surface-container-high overflow-hidden flex">
        <div
          class="h-full bg-secondary/80 transition-all duration-700"
          :style="{ width: pct(stats.converted, stats.total) + '%' }"
        />
        <div
          class="h-full bg-primary-container/60 transition-all duration-700"
          :style="{ width: pct(stats.human_review, stats.total) + '%' }"
        />
        <div
          v-if="stats.in_progress > 0"
          class="h-full bg-tertiary/70 transition-all duration-700"
          :style="{ width: pct(stats.in_progress, stats.total) + '%' }"
        />
      </div>
      <div class="flex justify-between text-[9px] font-mono text-zinc-600">
        <span>{{ pct(stats.converted, stats.total) }}% complete</span>
        <span>{{ stats.total.toLocaleString() }} total nodes</span>
      </div>
    </div>

    <!-- In-progress indicator -->
    <div v-if="stats && stats.in_progress > 0" class="flex items-center gap-2 text-[10px] font-mono text-tertiary">
      <span class="text-[8px] pulse-dot">●</span>
      <span>{{ stats.in_progress }} node{{ stats.in_progress !== 1 ? 's' : '' }} active</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { api, type StatsResponse } from '../api'
import { useRunStore } from '../store'

const store = useRunStore()
const stats = ref<StatsResponse | null>(null)
const error = ref('')

function pct(n: number, total: number): number {
  if (total === 0) return 0
  return Math.round(100 * n / total)
}

async function refresh() {
  try {
    stats.value = await api.getStats()
    error.value = ''
  } catch (e) {
    error.value = String(e)
  }
}

let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  refresh()
  timer = setInterval(() => {
    if (store.status === 'running' || store.status === 'idle') refresh()
  }, 5000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

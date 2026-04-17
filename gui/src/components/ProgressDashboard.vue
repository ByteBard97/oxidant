<template>
  <div class="flex flex-col gap-2 bg-surface-container-lowest p-3 border border-outline-variant/30">
    <div class="text-[10px] text-zinc-500 mb-1 tracking-widest">SESSION TELEMETRY</div>

    <!-- Segmented LED progress bar -->
    <div class="flex gap-[2px] h-2.5 w-full mb-1">
      <div
        v-for="i in totalSegments"
        :key="i"
        class="flex-1"
        :class="i <= filledSegments ? 'bg-secondary' : 'bg-surface-container-highest'"
      ></div>
    </div>

    <div class="flex justify-between items-center text-[10px] font-mono">
      <span class="text-zinc-400">CONVERTED</span>
      <span class="text-secondary font-bold">{{ store.stats.converted.toLocaleString() }}</span>
    </div>
    <div class="flex justify-between items-center text-[10px] font-mono">
      <span class="text-zinc-400">IN PROGRESS</span>
      <span class="text-white">{{ store.stats.inProgress }}</span>
    </div>
    <div class="flex justify-between items-center text-[10px] font-mono">
      <span class="text-zinc-400">NEEDS REVIEW</span>
      <span class="text-primary-container">{{ store.stats.needsReview }}</span>
    </div>

    <!-- Status badge -->
    <div class="mt-1 text-[10px] font-mono font-bold tracking-widest"
         :class="statusColor">
      [{{ store.status.toUpperCase() }}]
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRunStore } from '../store'

const store = useRunStore()

const totalSegments = 10
const filledSegments = computed(() => {
  const total = store.stats.converted + store.stats.needsReview + store.stats.inProgress
  if (total === 0) return 0
  const ratio = store.stats.converted / total
  return Math.round(ratio * totalSegments)
})

const statusColor = computed(() => {
  switch (store.status) {
    case 'running':    return 'text-secondary'
    case 'complete':   return 'text-secondary'
    case 'interrupted':return 'text-primary-container'
    case 'aborted':    return 'text-error'
    case 'paused':     return 'text-tertiary'
    default:           return 'text-zinc-500'
  }
})
</script>

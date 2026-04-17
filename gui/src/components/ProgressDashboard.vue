<template>
  <div class="flex flex-col gap-2 bg-surface-container-lowest p-3 border border-outline-variant/30">
    <div class="text-[10px] text-zinc-500 mb-1 tracking-widest">SESSION TELEMETRY</div>

    <!-- Segmented LED progress bar -->
    <Tooltip content="Translation progress — each segment = 10% of total nodes processed" position="right">
      <div class="flex gap-[2px] h-2.5 w-full mb-1 cursor-default">
        <div
          v-for="i in totalSegments"
          :key="i"
          class="flex-1"
          :class="i <= filledSegments ? 'bg-secondary' : 'bg-surface-container-highest'"
        ></div>
      </div>
    </Tooltip>

    <Tooltip content="Nodes successfully translated to Rust and written to disk" position="right">
      <div class="flex justify-between items-center text-[10px] font-mono cursor-default">
        <span class="text-zinc-400">CONVERTED</span>
        <span class="text-secondary font-bold">{{ store.stats.converted.toLocaleString() }}</span>
      </div>
    </Tooltip>
    <Tooltip content="Nodes currently being processed by an LLM tier" position="right">
      <div class="flex justify-between items-center text-[10px] font-mono cursor-default">
        <span class="text-zinc-400">IN PROGRESS</span>
        <span class="text-white">{{ store.stats.inProgress }}</span>
      </div>
    </Tooltip>
    <Tooltip content="Nodes that failed all tiers and are waiting for operator review" position="right">
      <div class="flex justify-between items-center text-[10px] font-mono cursor-default">
        <span class="text-zinc-400">NEEDS REVIEW</span>
        <span class="text-primary-container">{{ store.stats.needsReview }}</span>
      </div>
    </Tooltip>

    <Tooltip :content="statusDescription" position="right">
      <div class="mt-1 text-[10px] font-mono font-bold tracking-widest cursor-default"
           :class="statusColor">
        [{{ store.status.toUpperCase() }}]
      </div>
    </Tooltip>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRunStore } from '../store'
import Tooltip from './Tooltip.vue'

const store = useRunStore()

const totalSegments = 10
const filledSegments = computed(() => {
  const total = store.stats.converted + store.stats.needsReview + store.stats.inProgress
  if (total === 0) return 0
  return Math.round((store.stats.converted / total) * totalSegments)
})

const statusColor = computed(() => {
  switch (store.status) {
    case 'running':     return 'text-secondary'
    case 'complete':    return 'text-secondary'
    case 'interrupted': return 'text-primary-container'
    case 'aborted':     return 'text-error'
    case 'paused':      return 'text-tertiary'
    default:            return 'text-zinc-500'
  }
})

const statusDescription = computed(() => {
  switch (store.status) {
    case 'idle':        return 'No run active — configure paths and initiate sequence'
    case 'running':     return 'Translation pipeline active — nodes being processed'
    case 'paused':      return 'Run paused — LangGraph checkpoint saved, resume any time'
    case 'interrupted': return 'Halted — a node needs operator input before continuing'
    case 'complete':    return 'Run finished — all nodes processed'
    case 'aborted':     return 'Run aborted — state discarded, cannot be resumed'
    case 'error':       return 'Unrecoverable error — check server logs'
    default:            return store.status
  }
})
</script>

<template>
  <div class="flex-1 flex flex-col overflow-y-auto bg-surface-container-low p-8 gap-8 font-mono">

    <!-- Section: Paths -->
    <div class="flex flex-col gap-4">
      <div class="text-[10px] text-zinc-500 tracking-widest border-b border-dashed border-outline-variant/30 pb-2">
        INPUT / OUTPUT PATHS
      </div>

      <div class="flex flex-col gap-1">
        <label class="text-[10px] text-zinc-500 uppercase tracking-widest">Manifest Path</label>
        <Tooltip content="Path to conversion_manifest.json — lists all TS nodes to translate" position="right">
          <input
            v-model="store.manifestPath"
            class="w-full bg-surface-container-lowest border-l-2 border-transparent focus:border-primary outline-none text-sm font-mono text-zinc-200 px-3 py-2.5 placeholder-zinc-700 transition-colors"
            placeholder="/path/to/conversion_manifest.json"
          />
        </Tooltip>
      </div>

      <div class="flex flex-col gap-1">
        <label class="text-[10px] text-zinc-500 uppercase tracking-widest">Target Path</label>
        <Tooltip content="Root of the msagl-rs output repo — Rust files are written here" position="right">
          <input
            v-model="store.targetPath"
            class="w-full bg-surface-container-lowest border-l-2 border-transparent focus:border-primary outline-none text-sm font-mono text-zinc-200 px-3 py-2.5 placeholder-zinc-700 transition-colors"
            placeholder="/path/to/msagl-rs/"
          />
        </Tooltip>
      </div>
    </div>

    <!-- Section: Review mode -->
    <div class="flex flex-col gap-4">
      <div class="text-[10px] text-zinc-500 tracking-widest border-b border-dashed border-outline-variant/30 pb-2">
        REVIEW MODE
      </div>

      <div class="grid grid-cols-3 gap-3">
        <button
          v-for="opt in modeOptions" :key="opt.value"
          @click="store.reviewMode = opt.value"
          :disabled="store.status === 'running'"
          class="flex flex-col gap-2 p-4 border border-dashed text-left transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          :class="store.reviewMode === opt.value
            ? 'border-secondary bg-secondary/10 text-secondary'
            : 'border-outline-variant/30 text-zinc-500 hover:border-outline-variant hover:text-zinc-300'"
        >
          <span class="text-[11px] font-bold tracking-widest uppercase">{{ opt.label }}</span>
          <span class="text-[10px] leading-relaxed" :class="store.reviewMode === opt.value ? 'text-zinc-300' : 'text-zinc-600'">
            {{ opt.description }}
          </span>
        </button>
      </div>
    </div>

    <!-- Section: Run controls -->
    <div class="flex flex-col gap-3">
      <div class="text-[10px] text-zinc-500 tracking-widest border-b border-dashed border-outline-variant/30 pb-2">
        SEQUENCE CONTROL
      </div>

      <Tooltip content="Start a new translation run (or resume a paused one)" position="right">
        <button
          @click="start"
          :disabled="store.status === 'running'"
          class="grungy-cta w-full text-on-primary font-bold py-3 px-4 text-sm font-mono uppercase tracking-widest flex justify-center items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <span class="material-symbols-outlined text-[18px]" style="font-variation-settings: 'FILL' 1">bolt</span>
          {{ store.status === 'paused' ? '[RESUME_SEQUENCE]' : '[INITIATE_SEQUENCE]' }}
        </button>
      </Tooltip>

      <div class="flex gap-3">
        <Tooltip content="Pause — checkpoints current state. Can be resumed." position="top">
          <button
            @click="pause"
            :disabled="store.status !== 'running'"
            class="flex-1 bg-surface-container-high border border-outline-variant/50 text-zinc-400 hover:text-white py-2.5 flex justify-center items-center gap-2 text-xs font-mono uppercase tracking-widest disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <span class="material-symbols-outlined text-[16px]">pause</span>
            Pause
          </button>
        </Tooltip>
        <Tooltip content="Abort — terminates immediately. Cannot be resumed." position="top">
          <button
            @click="abort"
            :disabled="store.status === 'idle' || store.status === 'complete' || store.status === 'aborted'"
            class="flex-1 bg-surface-container-high border border-outline-variant/50 text-primary-container hover:bg-primary-container/10 py-2.5 flex justify-center items-center gap-2 text-xs font-mono uppercase tracking-widest disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <span class="material-symbols-outlined text-[16px]">stop</span>
            Abort
          </button>
        </Tooltip>
      </div>
    </div>

    <div v-if="error" class="text-error text-[10px] font-mono border-l-2 border-error pl-3">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { useRunStore } from '../store'
import { useRunActions } from '../composables/useRunActions'
import Tooltip from './Tooltip.vue'

const store = useRunStore()
const { start, pause, abort, error } = useRunActions()

const modeOptions = [
  {
    value: 'auto' as const,
    label: 'Auto',
    description: 'Supervisor decides autonomously. Human only sees nodes that exhaust all tiers.',
  },
  {
    value: 'supervised' as const,
    label: 'Supervised',
    description: 'Supervisor hints every node before translation. Slower but higher quality.',
  },
  {
    value: 'interactive' as const,
    label: 'Interactive',
    description: 'Human approves every node. Full control. Use for critical or complex files.',
  },
]
</script>

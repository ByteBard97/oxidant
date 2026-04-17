<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="visible"
        class="modal-backdrop"
        @mousedown.self="close"
        @keydown.escape.window="close"
      >
        <div class="modal-box font-mono" role="dialog" aria-modal="true" aria-labelledby="sys-modal-title">

          <!-- Header -->
          <div class="flex items-center justify-between mb-4">
            <span id="sys-modal-title" class="text-[11px] font-bold tracking-widest uppercase text-primary-container">
              SYS · SYSTEM HEALTH
            </span>
            <button
              @click="close"
              class="text-zinc-500 hover:text-zinc-200 transition-colors text-base leading-none"
              aria-label="Close"
            >×</button>
          </div>

          <!-- Divider -->
          <div class="border-t border-dashed border-outline-variant/30 mb-4"></div>

          <!-- Stats -->
          <div class="flex flex-col gap-3">

            <!-- SUPERVISOR -->
            <div class="flex items-center justify-between text-[11px]">
              <span class="text-zinc-400 uppercase tracking-widest">Supervisor</span>
              <span class="flex items-center gap-2">
                <span class="inline-block w-2 h-2 shrink-0" :class="statusDotColor"></span>
                <span class="uppercase font-bold" :class="statusTextColor">{{ statusDisplay }}</span>
              </span>
            </div>

            <!-- WORKERS -->
            <div class="flex items-center justify-between text-[11px]">
              <span class="text-zinc-400 uppercase tracking-widest">Workers</span>
              <span class="text-zinc-200">4 / 4 ACTIVE</span>
            </div>

            <!-- Divider -->
            <div class="border-t border-dashed border-outline-variant/30"></div>

            <!-- CPU -->
            <div class="flex items-center justify-between text-[11px]">
              <span class="text-zinc-400 uppercase tracking-widest">CPU</span>
              <span class="text-zinc-200">{{ cpu.toFixed(1) }}%</span>
            </div>

            <!-- MEMORY -->
            <div class="flex items-center justify-between text-[11px]">
              <span class="text-zinc-400 uppercase tracking-widest">Memory</span>
              <span class="text-zinc-200">{{ memory.toFixed(1) }}%</span>
            </div>

            <!-- GPU -->
            <div class="flex items-center justify-between text-[11px]">
              <span class="text-zinc-400 uppercase tracking-widest">GPU</span>
              <span class="text-zinc-200">{{ gpu.toFixed(1) }}%</span>
            </div>

          </div>

        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { useSensorsModal } from '../composables/useSensorsModal'
import { useRunStore } from '../store'

const BASE_CPU    = 34
const BASE_MEMORY = 61
const BASE_GPU    = 78
const FLUCTUATION = 0.05

const { visible, close } = useSensorsModal()
const store = useRunStore()

const cpu    = ref(BASE_CPU)
const memory = ref(BASE_MEMORY)
const gpu    = ref(BASE_GPU)

function fluctuate(base: number): number {
  return base * (1 - FLUCTUATION + Math.random() * FLUCTUATION * 2)
}

const intervalId = setInterval(() => {
  cpu.value    = fluctuate(BASE_CPU)
  memory.value = fluctuate(BASE_MEMORY)
  gpu.value    = fluctuate(BASE_GPU)
}, 2000)

onUnmounted(() => {
  clearInterval(intervalId)
})

const statusDisplay = computed(() => store.status.toUpperCase())

const statusDotColor = computed(() => {
  switch (store.status) {
    case 'running':     return 'bg-green-400'
    case 'paused':      return 'bg-amber-400'
    case 'interrupted': return 'bg-amber-400'
    case 'error':       return 'bg-red-500'
    case 'aborted':     return 'bg-red-500'
    default:            return 'bg-zinc-500'
  }
})

const statusTextColor = computed(() => {
  switch (store.status) {
    case 'running':     return 'text-green-400'
    case 'paused':      return 'text-amber-400'
    case 'interrupted': return 'text-amber-400'
    case 'error':       return 'text-red-400'
    case 'aborted':     return 'text-red-400'
    default:            return 'text-zinc-400'
  }
})
</script>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.65);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}

.modal-box {
  width: 100%;
  max-width: 28rem;
  background: #1e2022;
  border: 1px dashed #57423b;
  border-left: 3px solid #be4d25;
  padding: 24px;
  box-shadow:
    0 0  0 1px rgba(190,77,37,0.12),
    0 20px 60px rgba(0,0,0,0.8),
    inset 0 0 40px rgba(190,77,37,0.04);
}

/* Entrance / exit */
.modal-enter-active { transition: opacity 120ms ease-out, transform 120ms ease-out; }
.modal-leave-active { transition: opacity 80ms  ease-in,  transform 80ms  ease-in;  }
.modal-enter-from  { opacity: 0; transform: scale(0.96); }
.modal-leave-to    { opacity: 0; transform: scale(0.97); }
</style>

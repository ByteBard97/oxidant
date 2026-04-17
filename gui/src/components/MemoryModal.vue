<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="visible"
        class="modal-backdrop"
        @mousedown.self="close"
        @keydown.escape.window="close"
      >
        <div class="modal-box font-mono" role="dialog" aria-modal="true" aria-labelledby="mem-modal-title">

          <!-- Header -->
          <div class="flex items-center justify-between mb-4">
            <span id="mem-modal-title" class="text-[11px] font-bold tracking-widest uppercase text-primary-container">
              MEM · ACTIVE CONTEXTS
            </span>
            <button
              @click="close"
              class="text-zinc-500 hover:text-zinc-200 transition-colors text-base leading-none"
              aria-label="Close"
            >×</button>
          </div>

          <!-- Divider -->
          <div class="border-t border-dashed border-outline-variant/30 mb-4"></div>

          <!-- NODE CONTEXTS section -->
          <div class="mb-5">
            <div class="text-[10px] tracking-widest uppercase text-zinc-500 mb-2">Node Contexts</div>

            <div v-if="nodeList.length === 0" class="text-[11px] text-zinc-600 font-mono">
              — no active contexts —
            </div>

            <div v-else class="flex flex-col gap-1">
              <div
                v-for="node in nodeList"
                :key="node.node_id"
                class="flex items-center justify-between text-[11px]"
              >
                <span class="text-zinc-300 truncate mr-3">{{ shortId(node.node_id) }}</span>
                <span
                  class="shrink-0 text-[10px] font-bold tracking-widest uppercase"
                  :class="tierColor(node.tier)"
                >{{ node.tier.toUpperCase() }}</span>
              </div>
            </div>
          </div>

          <!-- Divider -->
          <div class="border-t border-dashed border-outline-variant/30 mb-4"></div>

          <!-- TOKEN ESTIMATES section -->
          <div>
            <div class="text-[10px] tracking-widest uppercase text-zinc-500 mb-2">Token Estimates</div>

            <div class="flex flex-col gap-1 text-[11px]">
              <div class="flex justify-between">
                <span class="text-zinc-400 uppercase tracking-widest">Haiku/Sonnet contexts</span>
                <span class="text-zinc-200">{{ cheapCount }} × ~8k = {{ cheapCount * 8 }}k</span>
              </div>
              <div class="flex justify-between">
                <span class="text-zinc-400 uppercase tracking-widest">Opus contexts</span>
                <span class="text-zinc-200">{{ opusCount }} × ~12k = {{ opusCount * 12 }}k</span>
              </div>
              <div class="border-t border-dashed border-outline-variant/30 mt-2 pt-2 flex justify-between">
                <span class="text-zinc-400 uppercase tracking-widest font-bold">Total</span>
                <span class="text-primary-container font-bold">~{{ totalTokens }}k tokens</span>
              </div>
            </div>
          </div>

        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useMemoryModal } from '../composables/useMemoryModal'
import { useRunStore } from '../store'
import { shortId } from '../utils/strings'

const { visible, close } = useMemoryModal()
const store = useRunStore()

const nodeList = computed(() => Object.values(store.activeNodes))

const cheapCount = computed(() =>
  nodeList.value.filter(n => n.tier !== 'opus').length
)

const opusCount = computed(() =>
  nodeList.value.filter(n => n.tier === 'opus').length
)

const totalTokens = computed(() =>
  cheapCount.value * 8 + opusCount.value * 12
)

function tierColor(tier: string): string {
  if (tier === 'opus') return 'text-primary-container'
  return 'text-secondary'
}
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

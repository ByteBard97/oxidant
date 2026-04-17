<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="visible"
        class="modal-backdrop"
        @mousedown.self="cancel"
      >
        <div class="modal-box font-mono" role="alertdialog" aria-modal="true" :aria-labelledby="'modal-title'">

          <!-- Header -->
          <div class="flex items-center gap-3 mb-4">
            <span class="material-symbols-outlined text-primary-container text-[22px] shrink-0">warning</span>
            <span id="modal-title" class="text-[11px] font-bold tracking-widest uppercase text-primary-container">
              {{ title }}
            </span>
          </div>

          <!-- Divider -->
          <div class="border-t border-dashed border-outline-variant/30 mb-4"></div>

          <!-- Message -->
          <p class="text-sm text-zinc-300 leading-relaxed mb-6 font-mono">{{ message }}</p>

          <!-- Actions -->
          <div class="flex gap-3 justify-end">
            <button
              @click="cancel"
              class="px-4 py-2 text-xs font-mono font-bold uppercase tracking-widest
                     text-zinc-400 bg-surface-container-lowest
                     border border-dashed border-outline-variant/50
                     hover:text-white hover:border-outline-variant
                     transition-colors"
            >
              Cancel
            </button>
            <button
              @click="accept"
              class="px-4 py-2 text-xs font-mono font-bold uppercase tracking-widest
                     text-on-primary bg-primary-container
                     border-b-2 border-[#8a2a10]
                     hover:brightness-110 transition-all"
            >
              Skip Node
            </button>
          </div>

        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { useConfirm } from '../composables/useConfirm'
const { visible, title, message, accept, cancel } = useConfirm()
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
  width: 420px;
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

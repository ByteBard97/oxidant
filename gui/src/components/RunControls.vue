<template>
  <div class="flex flex-col gap-3">
    <!-- Path inputs -->
    <div class="flex flex-col gap-2">
      <input
        v-model="manifestPath"
        class="w-full bg-surface-container-lowest border-0 border-l-2 border-transparent focus:border-primary outline-none text-[11px] font-mono text-zinc-300 px-2 py-1.5 placeholder-zinc-600 transition-colors"
        placeholder="MANIFEST PATH"
      />
      <input
        v-model="targetPath"
        class="w-full bg-surface-container-lowest border-0 border-l-2 border-transparent focus:border-primary outline-none text-[11px] font-mono text-zinc-300 px-2 py-1.5 placeholder-zinc-600 transition-colors"
        placeholder="TARGET PATH"
      />
      <select
        v-model="store.reviewMode"
        :disabled="store.status === 'running'"
        class="w-full bg-surface-container-lowest text-[11px] font-mono text-zinc-300 px-2 py-1.5 border-0 outline-none"
      >
        <option value="auto">MODE: AUTO</option>
        <option value="supervised">MODE: SUPERVISED</option>
        <option value="interactive">MODE: INTERACTIVE</option>
      </select>
    </div>

    <!-- Primary CTA — grungy stamped-metal button -->
    <button
      @click="start"
      :disabled="store.status === 'running'"
      class="grungy-cta w-full text-on-primary font-bold py-2.5 px-4 text-xs font-mono uppercase tracking-widest flex justify-center items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
    >
      <span class="material-symbols-outlined text-[16px]" style="font-variation-settings: 'FILL' 1">bolt</span>
      {{ store.status === 'paused' ? '[RESUME_SEQUENCE]' : '[INITIATE_SEQUENCE]' }}
    </button>

    <!-- Secondary controls -->
    <div class="flex gap-2">
      <button
        @click="pause"
        :disabled="store.status !== 'running'"
        title="Pause"
        class="flex-1 bg-surface-container-high border border-outline-variant text-zinc-400 hover:text-white py-1.5 flex justify-center items-center disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <span class="material-symbols-outlined text-[16px]">pause</span>
      </button>
      <button
        @click="abort"
        :disabled="store.status === 'idle' || store.status === 'complete' || store.status === 'aborted'"
        title="Abort"
        class="flex-1 bg-surface-container-high border border-outline-variant text-primary-container hover:bg-primary-container/10 py-1.5 flex justify-center items-center disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <span class="material-symbols-outlined text-[16px]">stop</span>
      </button>
    </div>

    <div v-if="error" class="text-error text-[10px] font-mono">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRunStore } from '../store'
import { api } from '../api'
import { connectSSE, disconnectSSE } from '../sse'

const store = useRunStore()
const manifestPath = ref('')
const targetPath = ref('')
const error = ref('')

async function start() {
  error.value = ''
  try {
    const res = await api.startRun({
      manifest_path: manifestPath.value,
      target_path: targetPath.value,
      review_mode: store.reviewMode,
      thread_id: store.status === 'paused' ? store.threadId : null,
    })
    store.setThreadId(res.thread_id)
    connectSSE(res.thread_id)
  } catch (e) {
    error.value = String(e)
  }
}

async function pause() {
  if (!store.threadId) return
  try {
    await api.pauseRun(store.threadId)
    store.setStatus('paused')
    disconnectSSE()
  } catch (e) {
    error.value = String(e)
  }
}

async function abort() {
  if (!store.threadId) return
  if (!confirm('Abort this run? It cannot be resumed.')) return
  try {
    await api.abortRun(store.threadId)
    store.setStatus('aborted')
    disconnectSSE()
  } catch (e) {
    error.value = String(e)
  }
}
</script>

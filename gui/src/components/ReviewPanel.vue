<template>
  <div class="w-[450px] bg-surface flex flex-col shrink-0 border-l-4 shadow-[-10px_0_20px_rgba(0,0,0,0.5)]"
       :class="store.pendingReview ? 'border-primary-container' : 'border-outline-variant/30'">

    <!-- Header -->
    <div class="px-4 bg-surface-container-high border-b border-[#2D2F31] flex justify-between items-center shrink-0 min-h-[84px]">
      <div class="flex items-center gap-2">
        <span class="material-symbols-outlined text-primary-container text-[18px]">warning</span>
        <h2 class="font-headline font-bold text-sm tracking-wide text-white uppercase">Manual Review Required</h2>
      </div>
      <Tooltip content="AUTO: pass most nodes. SUPERVISED: hint every node. INTERACTIVE: you approve each one." position="left">
        <select
          v-model="store.reviewMode"
          class="bg-surface-container-lowest border border-outline-variant text-xs font-mono text-zinc-300 py-1 px-2 focus:outline-none focus:border-primary"
        >
          <option value="auto">AUTO (Permissive)</option>
          <option value="supervised">SUPERVISED</option>
          <option value="interactive">INTERACTIVE (All Nodes)</option>
        </select>
      </Tooltip>
    </div>

    <!-- Idle state -->
    <div v-if="!store.pendingReview" class="flex-1 flex flex-col items-center justify-center p-8 gap-4 text-center">
      <span class="material-symbols-outlined text-zinc-700 text-[48px]">checklist</span>
      <div class="font-mono text-[11px] text-zinc-600 uppercase tracking-widest">No Review Pending</div>
      <div class="font-mono text-[10px] text-zinc-700">Nodes will appear here when<br/>manual review is required.</div>
    </div>

    <!-- Active review content -->
    <div v-else class="flex-1 overflow-y-auto p-4 flex flex-col gap-5">

      <!-- Error summary -->
      <div class="bg-surface-container-lowest border-l-2 border-primary-container p-3 font-mono text-xs text-zinc-200">
        <div class="text-primary-container mb-1 font-bold text-[10px] tracking-widest">
          ERR · {{ shortId(store.pendingReview.node_id) }}
        </div>
        <pre class="whitespace-pre-wrap text-zinc-300 leading-relaxed">{{ store.pendingReview.error }}</pre>
      </div>

      <!-- Source preview -->
      <div class="flex flex-col shadow-md">
        <div class="bg-[#2D2F31] px-3 py-1 flex justify-between items-center text-[10px] font-mono text-zinc-400">
          <span>SOURCE (TS)</span>
          <span class="text-zinc-500">{{ shortId(store.pendingReview.node_id) }}</span>
        </div>
        <div class="bg-surface-container-lowest p-3 border border-outline-variant/20 overflow-auto max-h-52">
          <pre class="text-[11px] font-mono text-zinc-300 leading-relaxed whitespace-pre-wrap">{{ store.pendingReview.source_preview }}</pre>
        </div>
      </div>

      <!-- Resolution textarea -->
      <div class="flex flex-col gap-2 flex-1">
        <label class="text-xs font-mono text-zinc-400 uppercase tracking-widest">Operator Resolution</label>
        <textarea
          v-model="hint"
          rows="5"
          class="w-full bg-surface-container-lowest border-l-2 border-transparent focus:border-primary outline-dashed outline-1 outline-outline-variant/30 text-sm font-mono text-white p-3 resize-none transition-colors focus:outline-none"
          placeholder="Enter Rust type override or translation hint..."
        />
      </div>

      <!-- Action buttons -->
      <div class="flex gap-3">
        <button
          @click="skip"
          :disabled="submitting"
          class="flex-1 bg-surface-container-highest text-primary border border-dashed border-outline-variant py-2 text-sm font-mono font-bold hover:bg-surface-bright transition-colors uppercase disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Skip Node
        </button>
        <button
          @click="resume"
          :disabled="submitting"
          class="flex-1 bg-gradient-to-r from-secondary-container to-[#033d36] text-on-secondary-container border-b-2 border-[#022b26] py-2 text-sm font-mono font-bold hover:opacity-90 transition-opacity uppercase disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {{ submitting ? 'Applying…' : 'Apply Fix' }}
        </button>
      </div>

      <div v-if="error" class="text-error text-[10px] font-mono">{{ error }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRunStore } from '../store'
import { api } from '../api'
import { connectSSE } from '../sse'

const store = useRunStore()
const hint = ref('')
const submitting = ref(false)
const error = ref('')

watch(
  () => store.pendingReview,
  (payload) => { hint.value = payload?.supervisor_hint ?? '' },
  { immediate: true },
)

function shortId(id: string): string {
  const parts = id.split('/')
  return '...' + parts.slice(-2).join('/')
}

async function resume() {
  if (!store.threadId || !store.pendingReview) return
  submitting.value = true
  error.value = ''
  try {
    await api.resumeInterrupt(store.threadId, hint.value, false)
    store.clearReview()
    store.setStatus('running')
    connectSSE(store.threadId)
  } catch (e) {
    error.value = String(e)
  } finally {
    submitting.value = false
  }
}

async function skip() {
  if (!store.threadId || !store.pendingReview) return
  if (!confirm('Skip this node? It will be queued for human review.')) return
  submitting.value = true
  error.value = ''
  try {
    await api.resumeInterrupt(store.threadId, '', true)
    store.clearReview()
    store.setStatus('running')
    connectSSE(store.threadId)
  } catch (e) {
    error.value = String(e)
  } finally {
    submitting.value = false
  }
}
</script>

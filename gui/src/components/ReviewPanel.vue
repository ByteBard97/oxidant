<template>
  <div v-if="store.status === 'interrupted' && store.pendingReview" class="review-panel">
    <div class="panel-header">Review Required</div>

    <div class="section">
      <div class="section-title">Node</div>
      <div class="node-id">{{ store.pendingReview.node_id }}</div>
    </div>

    <div class="section">
      <div class="section-title">Error</div>
      <pre class="error-text">{{ store.pendingReview.error }}</pre>
    </div>

    <div class="section">
      <div class="section-title">Source preview</div>
      <pre class="source-text">{{ store.pendingReview.source_preview }}</pre>
    </div>

    <div class="section">
      <div class="section-title">Supervisor hint (editable)</div>
      <textarea v-model="hint" rows="4" class="hint-input" />
    </div>

    <div class="button-row">
      <button @click="resume" class="btn btn-resume" :disabled="submitting">
        {{ submitting ? 'Resuming…' : 'Resume with hint' }}
      </button>
      <button @click="skip" class="btn btn-skip" :disabled="submitting">
        Skip this node
      </button>
    </div>
    <div v-if="error" class="error-msg">{{ error }}</div>
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

// Pre-fill hint when a new review arrives
watch(
  () => store.pendingReview,
  (payload) => {
    hint.value = payload?.supervisor_hint ?? ''
  },
  { immediate: true },
)

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

<style scoped>
.review-panel {
  position: fixed; right: 0; top: 0; bottom: 0; width: 420px;
  background: #0a0a0a; border-left: 2px solid #f97316;
  padding: 20px; overflow-y: auto; z-index: 100;
}
.panel-header { font-size: 14px; font-weight: bold; color: #f97316; margin-bottom: 16px; }
.section { margin-bottom: 16px; }
.section-title { font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }
.node-id { font-size: 13px; color: #60a5fa; word-break: break-all; }
.error-text, .source-text {
  font-size: 12px; background: #1a1a1a; padding: 8px; border-radius: 4px;
  max-height: 120px; overflow-y: auto; white-space: pre-wrap; color: #fca5a5;
}
.source-text { color: #a3e635; }
.hint-input {
  width: 100%; background: #1a1a1a; border: 1px solid #444; color: #e5e5e5;
  padding: 8px; border-radius: 4px; font-family: inherit; font-size: 13px;
  resize: vertical;
}
.button-row { display: flex; gap: 8px; margin-top: 8px; }
.btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; font-family: inherit; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-resume { background: #166534; color: #fff; }
.btn-skip { background: #3b0764; color: #fff; }
.error-msg { margin-top: 8px; color: #f87171; font-size: 12px; }
</style>

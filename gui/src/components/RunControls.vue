<template>
  <div class="run-controls">
    <div class="control-row">
      <label for="manifest-path">Manifest:</label>
      <input id="manifest-path" v-model="manifestPath" placeholder="/path/to/conversion_manifest.json" />
    </div>
    <div class="control-row">
      <label for="target-path">Target:</label>
      <input id="target-path" v-model="targetPath" placeholder="/path/to/msagl-rs" />
    </div>
    <div class="control-row">
      <label>Review mode:</label>
      <select v-model="store.reviewMode" :disabled="store.status === 'running'">
        <option value="auto">auto</option>
        <option value="supervised">supervised</option>
        <option value="interactive">interactive</option>
      </select>
    </div>
    <div class="button-row">
      <button
        @click="start"
        :disabled="store.status === 'running'"
        class="btn btn-start"
      >
        {{ store.status === 'paused' ? 'Resume' : 'Start' }}
      </button>
      <button
        @click="pause"
        :disabled="store.status !== 'running'"
        class="btn btn-pause"
      >Pause</button>
      <button
        @click="abort"
        :disabled="store.status === 'idle' || store.status === 'complete' || store.status === 'aborted'"
        class="btn btn-abort"
      >Abort</button>
    </div>
    <div v-if="error" class="error-msg">{{ error }}</div>
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

<style scoped>
.run-controls { padding: 16px; border-bottom: 1px solid #333; }
.control-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.control-row label { width: 90px; color: #aaa; font-size: 13px; }
.control-row input, .control-row select {
  flex: 1; background: #1a1a1a; border: 1px solid #444; color: #e5e5e5;
  padding: 4px 8px; border-radius: 4px; font-family: inherit; font-size: 13px;
}
.button-row { display: flex; gap: 8px; margin-top: 8px; }
.btn { padding: 6px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; font-family: inherit; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-start { background: #166534; color: #fff; }
.btn-pause { background: #92400e; color: #fff; }
.btn-abort { background: #7f1d1d; color: #fff; }
.error-msg { margin-top: 8px; color: #f87171; font-size: 12px; }
</style>

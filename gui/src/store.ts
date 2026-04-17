import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'

export type RunStatus = 'idle' | 'running' | 'paused' | 'interrupted' | 'complete' | 'aborted' | 'error'

export interface NodeProgress {
  node_id: string
  tier: string
  status: 'translating' | 'converted' | 'needs_review'
  attempts: number
  startedAt: number
}

export interface InterruptPayload {
  node_id: string
  error: string
  supervisor_hint: string
  source_preview: string
}

export interface RunStats {
  converted: number
  needsReview: number
  inProgress: number
}

// ── SSE event shapes (mirror events.py) ──────────────────────────────────────

interface NodeStartEvent { event: 'node_start'; node_id: string; tier: string }
interface NodeCompleteEvent { event: 'node_complete'; node_id: string; tier: string; attempts: number }
interface NodeEscalateEvent { event: 'node_escalate'; node_id: string; from_tier: string; to_tier: string }
interface SupervisorEventData { event: 'supervisor'; node_id: string; hint: string; requires_human: boolean }
interface InterruptEventData { event: 'interrupt'; node_id: string; payload: InterruptPayload }
interface RunCompleteEventData { event: 'run_complete'; converted: number; needs_review: number }
interface ErrorEventData { event: 'error'; node_id: string; message: string }
interface StatusEventData { event: 'status'; status: string; message: string }

type SSEEvent =
  | NodeStartEvent
  | NodeCompleteEvent
  | NodeEscalateEvent
  | SupervisorEventData
  | InterruptEventData
  | RunCompleteEventData
  | ErrorEventData
  | StatusEventData

export const useRunStore = defineStore('run', () => {
  const threadId = ref<string | null>(null)
  const status = ref<RunStatus>('idle')
  const reviewMode = ref<'auto' | 'interactive' | 'supervised'>('auto')
  const manifestPath = ref('')
  const targetPath = ref('')
  const activeNodes = reactive<Record<string, NodeProgress>>({})
  const pendingReview = ref<InterruptPayload | null>(null)
  const recentEvents = ref<string[]>([])
  const stats = reactive<RunStats>({ converted: 0, needsReview: 0, inProgress: 0 })

  function setThreadId(id: string) {
    threadId.value = id
    status.value = 'running'
  }

  function setStatus(s: RunStatus) {
    status.value = s
  }

  function applyEvent(raw: string) {
    let evt: SSEEvent
    try {
      evt = JSON.parse(raw) as SSEEvent
    } catch {
      return
    }
    recentEvents.value = [raw, ...recentEvents.value].slice(0, 50)

    switch (evt.event) {
      case 'node_start':
        applyNodeStart(evt)
        break
      case 'node_complete':
        applyNodeComplete(evt)
        break
      case 'node_escalate':
        applyNodeEscalate(evt)
        break
      case 'supervisor':
        break
      case 'interrupt':
        applyInterrupt(evt)
        break
      case 'run_complete':
        applyRunComplete(evt)
        break
      case 'error':
        if (activeNodes[evt.node_id]) {
          activeNodes[evt.node_id].status = 'needs_review'
          delete activeNodes[evt.node_id]
          stats.needsReview++
          stats.inProgress = Math.max(0, stats.inProgress - 1)
        }
        break
    }
  }

  function applyNodeStart(evt: { node_id: string; tier: string }) {
    activeNodes[evt.node_id] = {
      node_id: evt.node_id,
      tier: evt.tier,
      status: 'translating',
      attempts: 0,
      startedAt: Date.now(),
    }
    stats.inProgress++
  }

  function applyNodeComplete(evt: { node_id: string; tier: string; attempts: number }) {
    delete activeNodes[evt.node_id]
    stats.converted++
    stats.inProgress = Math.max(0, stats.inProgress - 1)
  }

  function applyNodeEscalate(evt: { node_id: string; from_tier: string; to_tier: string }) {
    if (activeNodes[evt.node_id]) {
      activeNodes[evt.node_id].tier = evt.to_tier
    }
  }

  function applyInterrupt(evt: { node_id: string; payload: InterruptPayload }) {
    status.value = 'interrupted'
    pendingReview.value = evt.payload
    stats.inProgress = Math.max(0, stats.inProgress - 1)
  }

  function applyRunComplete(evt: { converted: number; needs_review: number }) {
    status.value = 'complete'
    stats.converted = evt.converted
    stats.needsReview = evt.needs_review
    stats.inProgress = 0
  }

  function clearReview() {
    pendingReview.value = null
  }

  function reset() {
    threadId.value = null
    status.value = 'idle'
    Object.keys(activeNodes).forEach(k => delete activeNodes[k])
    pendingReview.value = null
    recentEvents.value = []
    stats.converted = 0
    stats.needsReview = 0
    stats.inProgress = 0
  }

  return {
    threadId, status, reviewMode, manifestPath, targetPath,
    activeNodes, pendingReview, recentEvents, stats,
    setThreadId, setStatus, applyEvent, applyNodeStart, applyNodeComplete,
    applyNodeEscalate, applyInterrupt, applyRunComplete, clearReview, reset,
  }
})

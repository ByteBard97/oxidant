# Oxidant GUI — Vue 3 Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Prerequisite:** `2026-04-16-phase-b-supervisor-api.md` must be complete. This plan assumes `oxidant serve` is running at `http://localhost:8000` with SSE and REST endpoints available.

**Goal:** Build a Vue 3 + Vite single-page dashboard that streams Phase B progress via SSE, shows run controls, and surfaces a review panel when `review_mode=interactive` and a supervisor interrupt fires.

**Architecture:** Vue 3 + Vite (TypeScript), Pinia for state, native `EventSource` for SSE. No component library — minimal custom CSS. Built to `gui/dist/`, served by FastAPI via `oxidant serve --gui-dist gui/dist`.

**Tech Stack:** Vue 3, Vite 5, TypeScript, Pinia, native browser EventSource, Vitest (unit tests)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `gui/package.json` | Node deps: vue, vite, pinia, @vitejs/plugin-vue, vitest, typescript |
| Create | `gui/vite.config.ts` | Vite config with Vue plugin + API proxy to :8000 |
| Create | `gui/tsconfig.json` | TypeScript config |
| Create | `gui/index.html` | HTML entry point |
| Create | `gui/src/main.ts` | App bootstrap: createApp + pinia |
| Create | `gui/src/App.vue` | Root layout: RunControls + ProgressDashboard + LiveNodeFeed + ReviewPanel |
| Create | `gui/src/api.ts` | Typed wrappers for REST calls (startRun, pause, abort, resume) |
| Create | `gui/src/store.ts` | Pinia `useRunStore`: all reactive run state |
| Create | `gui/src/sse.ts` | SSE client: connects EventSource, routes events into store |
| Create | `gui/src/components/RunControls.vue` | Start/Pause/Abort buttons + review_mode toggle |
| Create | `gui/src/components/ProgressDashboard.vue` | Counts: converted, needs_review, in_progress |
| Create | `gui/src/components/LiveNodeFeed.vue` | Scrolling list of recent node events |
| Create | `gui/src/components/ReviewPanel.vue` | Shown when status=interrupted: source, error, hint, text input, resume button |
| Create | `gui/src/tests/store.test.ts` | Vitest unit tests for store mutations |

---

### Task 1: Scaffold the Vite + Vue project

**Files:**
- Create: `gui/package.json`
- Create: `gui/vite.config.ts`
- Create: `gui/tsconfig.json`
- Create: `gui/index.html`
- Create: `gui/src/main.ts`

- [ ] **Step 1: Create gui/package.json**

```json
{
  "name": "oxidant-gui",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "vue": "^3.4.0",
    "pinia": "^2.1.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "typescript": "^5.4.0",
    "vite": "^5.2.0",
    "vitest": "^1.5.0",
    "vue-tsc": "^2.0.0",
    "@vue/test-utils": "^2.4.0",
    "jsdom": "^24.0.0",
    "@vitest/coverage-v8": "^1.5.0"
  }
}
```

- [ ] **Step 2: Create gui/vite.config.ts**

```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/run': 'http://localhost:8000',
      '/stream': 'http://localhost:8000',
      '/pause': 'http://localhost:8000',
      '/abort': 'http://localhost:8000',
      '/resume': 'http://localhost:8000',
      '/review-queue': 'http://localhost:8000',
      '/status': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
```

- [ ] **Step 3: Create gui/tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

- [ ] **Step 4: Create gui/index.html**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Oxidant</title>
    <style>
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body { font-family: ui-monospace, 'Cascadia Code', monospace; background: #0f0f0f; color: #e5e5e5; }
    </style>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

- [ ] **Step 5: Create gui/src/main.ts**

```typescript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'

const app = createApp(App)
app.use(createPinia())
app.mount('#app')
```

- [ ] **Step 6: Install and verify the dev server starts**

```bash
cd /Users/ceres/Desktop/SignalCanvas/oxidant/gui
npm install
npm run dev
```

Expected: `  ➜  Local:   http://localhost:5173/` — visit in browser, see blank page (no components yet).

Stop the server (Ctrl-C).

- [ ] **Step 7: Commit**

```bash
cd /Users/ceres/Desktop/SignalCanvas/oxidant
git add gui/
git commit -m "chore: scaffold Vue 3 + Vite GUI project"
```

---

### Task 2: Define types and the Pinia store

**Files:**
- Create: `gui/src/store.ts`
- Create: `gui/src/tests/store.test.ts`

- [ ] **Step 1: Create the test file**

```typescript
// gui/src/tests/store.test.ts
import { setActivePinia, createPinia } from 'pinia'
import { describe, it, expect, beforeEach } from 'vitest'
import { useRunStore } from '../store'

describe('useRunStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('starts in idle status', () => {
    const store = useRunStore()
    expect(store.status).toBe('idle')
    expect(store.threadId).toBeNull()
  })

  it('applyNodeStart adds node to activeNodes', () => {
    const store = useRunStore()
    store.applyNodeStart({ node_id: 'foo/bar', tier: 'haiku' })
    expect(store.activeNodes['foo/bar']).toBeDefined()
    expect(store.activeNodes['foo/bar'].tier).toBe('haiku')
    expect(store.activeNodes['foo/bar'].status).toBe('translating')
  })

  it('applyNodeComplete moves node from active to converted count', () => {
    const store = useRunStore()
    store.applyNodeStart({ node_id: 'foo/bar', tier: 'haiku' })
    store.applyNodeComplete({ node_id: 'foo/bar', tier: 'haiku', attempts: 1 })
    expect(store.activeNodes['foo/bar']).toBeUndefined()
    expect(store.stats.converted).toBe(1)
  })

  it('applyInterrupt sets status to interrupted and saves payload', () => {
    const store = useRunStore()
    store.setThreadId('t-123')
    store.applyInterrupt({
      node_id: 'n1',
      payload: { node_id: 'n1', error: 'boom', supervisor_hint: 'hint', source_preview: 'src' },
    })
    expect(store.status).toBe('interrupted')
    expect(store.pendingReview).not.toBeNull()
    expect(store.pendingReview!.supervisor_hint).toBe('hint')
  })

  it('applyRunComplete sets status to complete', () => {
    const store = useRunStore()
    store.applyRunComplete({ converted: 5, needs_review: 2 })
    expect(store.status).toBe('complete')
    expect(store.stats.converted).toBe(5)
    expect(store.stats.needsReview).toBe(2)
  })
})
```

- [ ] **Step 2: Run to verify tests fail**

```bash
cd gui && npm test
```

Expected: `Cannot find module '../store'`

- [ ] **Step 3: Create gui/src/store.ts**

```typescript
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
  const activeNodes = reactive<Record<string, NodeProgress>>({})
  const pendingReview = ref<InterruptPayload | null>(null)
  const recentEvents = ref<string[]>([])  // last 50 human-readable event strings
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
        // hint shown in LiveNodeFeed but no panel unless requires_human
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

  function applyNodeStart(evt: NodeStartEvent) {
    activeNodes[evt.node_id] = {
      node_id: evt.node_id,
      tier: evt.tier,
      status: 'translating',
      attempts: 0,
      startedAt: Date.now(),
    }
    stats.inProgress++
  }

  function applyNodeComplete(evt: NodeCompleteEvent) {
    delete activeNodes[evt.node_id]
    stats.converted++
    stats.inProgress = Math.max(0, stats.inProgress - 1)
  }

  function applyNodeEscalate(evt: NodeEscalateEvent) {
    if (activeNodes[evt.node_id]) {
      activeNodes[evt.node_id].tier = evt.to_tier
    }
  }

  function applyInterrupt(evt: InterruptEventData) {
    status.value = 'interrupted'
    pendingReview.value = evt.payload
    stats.inProgress = Math.max(0, stats.inProgress - 1)
  }

  function applyRunComplete(evt: RunCompleteEventData) {
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
    threadId, status, reviewMode, activeNodes, pendingReview, recentEvents, stats,
    setThreadId, setStatus, applyEvent, applyNodeStart, applyNodeComplete,
    applyNodeEscalate, applyInterrupt, applyRunComplete, clearReview, reset,
  }
})
```

- [ ] **Step 4: Run tests**

```bash
cd gui && npm test
```

Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/ceres/Desktop/SignalCanvas/oxidant
git add gui/src/store.ts gui/src/tests/store.test.ts
git commit -m "feat: add Pinia run store with SSE event handlers"
```

---

### Task 3: API client and SSE connector

**Files:**
- Create: `gui/src/api.ts`
- Create: `gui/src/sse.ts`

- [ ] **Step 1: Create gui/src/api.ts**

```typescript
/** Typed wrappers for the oxidant FastAPI REST endpoints. */

export interface StartRunRequest {
  manifest_path: string
  target_path: string
  snippets_dir?: string
  review_mode?: 'auto' | 'interactive' | 'supervised'
  max_nodes?: number | null
  thread_id?: string | null
}

export interface StartRunResponse {
  thread_id: string
  status: string
}

const BASE = ''  // same origin (proxied in dev, served directly in prod)

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) {
    const detail = await r.text()
    throw new Error(`POST ${path} → ${r.status}: ${detail}`)
  }
  return r.json() as Promise<T>
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`)
  if (!r.ok) {
    const detail = await r.text()
    throw new Error(`GET ${path} → ${r.status}: ${detail}`)
  }
  return r.json() as Promise<T>
}

export const api = {
  startRun: (req: StartRunRequest) =>
    post<StartRunResponse>('/run', req),

  pauseRun: (threadId: string) =>
    post<{ status: string }>(`/pause/${threadId}`),

  abortRun: (threadId: string) =>
    post<{ status: string }>(`/abort/${threadId}`),

  resumeInterrupt: (threadId: string, hint: string, skip = false) =>
    post<{ status: string }>(`/resume/${threadId}`, { hint, skip }),

  getStatus: (threadId: string) =>
    get<{ thread_id: string; status: string }>(`/status/${threadId}`),

  getReviewQueue: () =>
    get<unknown[]>('/review-queue'),
}
```

- [ ] **Step 2: Create gui/src/sse.ts**

```typescript
/** SSE client: connects EventSource, routes events into the Pinia run store. */
import { useRunStore } from './store'

let eventSource: EventSource | null = null

export function connectSSE(threadId: string): void {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }

  const store = useRunStore()
  eventSource = new EventSource(`/stream/${threadId}`)

  eventSource.onmessage = (e: MessageEvent<string>) => {
    store.applyEvent(e.data)
  }

  eventSource.onerror = () => {
    // EventSource auto-reconnects; close it if the run is done
    const s = store.status
    if (s === 'complete' || s === 'aborted' || s === 'error') {
      disconnectSSE()
    }
  }
}

export function disconnectSSE(): void {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add gui/src/api.ts gui/src/sse.ts
git commit -m "feat: add API client and SSE connector"
```

---

### Task 4: Build RunControls component

**Files:**
- Create: `gui/src/components/RunControls.vue`

- [ ] **Step 1: Create gui/src/components/RunControls.vue**

```vue
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
```

- [ ] **Step 2: Commit**

```bash
git add gui/src/components/RunControls.vue
git commit -m "feat: add RunControls component (start/pause/abort + review_mode toggle)"
```

---

### Task 5: Build ProgressDashboard and LiveNodeFeed

**Files:**
- Create: `gui/src/components/ProgressDashboard.vue`
- Create: `gui/src/components/LiveNodeFeed.vue`

- [ ] **Step 1: Create gui/src/components/ProgressDashboard.vue**

```vue
<template>
  <div class="progress-dashboard">
    <div class="stat-row">
      <div class="stat">
        <span class="stat-value converted">{{ store.stats.converted }}</span>
        <span class="stat-label">converted</span>
      </div>
      <div class="stat">
        <span class="stat-value in-progress">{{ store.stats.inProgress }}</span>
        <span class="stat-label">in progress</span>
      </div>
      <div class="stat">
        <span class="stat-value needs-review">{{ store.stats.needsReview }}</span>
        <span class="stat-label">needs review</span>
      </div>
    </div>
    <div class="status-badge" :class="store.status">{{ store.status }}</div>
  </div>
</template>

<script setup lang="ts">
import { useRunStore } from '../store'
const store = useRunStore()
</script>

<style scoped>
.progress-dashboard { padding: 16px; border-bottom: 1px solid #333; }
.stat-row { display: flex; gap: 32px; }
.stat { display: flex; flex-direction: column; align-items: center; }
.stat-value { font-size: 28px; font-weight: bold; }
.stat-value.converted { color: #4ade80; }
.stat-value.in-progress { color: #60a5fa; }
.stat-value.needs-review { color: #f97316; }
.stat-label { font-size: 11px; color: #888; margin-top: 2px; }
.status-badge { display: inline-block; margin-top: 12px; padding: 2px 10px;
  border-radius: 4px; font-size: 12px; background: #1a1a1a; border: 1px solid #444; }
.status-badge.running { border-color: #60a5fa; color: #60a5fa; }
.status-badge.complete { border-color: #4ade80; color: #4ade80; }
.status-badge.interrupted { border-color: #f97316; color: #f97316; }
.status-badge.aborted { border-color: #f87171; color: #f87171; }
.status-badge.paused { border-color: #a78bfa; color: #a78bfa; }
</style>
```

- [ ] **Step 2: Create gui/src/components/LiveNodeFeed.vue**

```vue
<template>
  <div class="live-feed">
    <div class="feed-title">Live feed</div>
    <div v-if="store.stats.inProgress > 0" class="active-nodes">
      <div v-for="node in activeNodeList" :key="node.node_id" class="active-node">
        <span class="spinner">⟳</span>
        <span class="node-id">{{ shortId(node.node_id) }}</span>
        <span class="tier-badge" :class="node.tier">{{ node.tier }}</span>
      </div>
    </div>
    <div class="event-log">
      <div v-for="(evt, i) in parsedEvents" :key="i" class="event-line">
        <span class="evt-icon">{{ eventIcon(evt.event) }}</span>
        <span class="evt-text">{{ formatEvent(evt) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRunStore } from '../store'

const store = useRunStore()

const activeNodeList = computed(() => Object.values(store.activeNodes))

const parsedEvents = computed(() => {
  return store.recentEvents.slice(0, 20).map(raw => {
    try { return JSON.parse(raw) } catch { return { event: 'unknown' } }
  })
})

function shortId(id: string): string {
  const parts = id.split('/')
  return parts.slice(-2).join('/')
}

function eventIcon(evt: string): string {
  const icons: Record<string, string> = {
    node_start: '▶', node_complete: '✓', node_escalate: '↑',
    supervisor: '🔍', interrupt: '⏸', error: '✗', run_complete: '★',
  }
  return icons[evt] ?? '·'
}

function formatEvent(evt: Record<string, unknown>): string {
  const e = evt.event as string
  if (e === 'node_start') return `${shortId(evt.node_id as string)} [${evt.tier}]`
  if (e === 'node_complete') return `${shortId(evt.node_id as string)} converted (${evt.attempts} attempts)`
  if (e === 'node_escalate') return `${shortId(evt.node_id as string)} escalated ${evt.from_tier}→${evt.to_tier}`
  if (e === 'supervisor') return `supervisor hint for ${shortId(evt.node_id as string)}`
  if (e === 'interrupt') return `review required: ${shortId(evt.node_id as string)}`
  if (e === 'error') return `FAILED: ${shortId(evt.node_id as string)}`
  if (e === 'run_complete') return `run complete — ${evt.converted} converted, ${evt.needs_review} for review`
  return e
}
</script>

<style scoped>
.live-feed { padding: 16px; flex: 1; overflow: hidden; display: flex; flex-direction: column; }
.feed-title { font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; }
.active-nodes { margin-bottom: 12px; }
.active-node { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 13px; }
.spinner { animation: spin 1s linear infinite; display: inline-block; color: #60a5fa; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.node-id { color: #e5e5e5; }
.tier-badge { font-size: 10px; padding: 1px 6px; border-radius: 3px; }
.tier-badge.haiku { background: #1e3a5f; color: #93c5fd; }
.tier-badge.sonnet { background: #3b0764; color: #d8b4fe; }
.tier-badge.opus { background: #7f1d1d; color: #fca5a5; }
.event-log { overflow-y: auto; flex: 1; }
.event-line { display: flex; gap: 8px; padding: 2px 0; font-size: 12px; border-bottom: 1px solid #1a1a1a; }
.evt-icon { width: 16px; flex-shrink: 0; text-align: center; }
.evt-text { color: #aaa; }
</style>
```

- [ ] **Step 3: Commit**

```bash
git add gui/src/components/ProgressDashboard.vue gui/src/components/LiveNodeFeed.vue
git commit -m "feat: add ProgressDashboard and LiveNodeFeed components"
```

---

### Task 6: Build ReviewPanel component

**Files:**
- Create: `gui/src/components/ReviewPanel.vue`

The review panel is only visible when `store.status === 'interrupted'` and `store.pendingReview !== null`. It shows the supervisor hint pre-filled in a textarea that the user can edit, plus a submit button and a "skip this node" button.

- [ ] **Step 1: Create gui/src/components/ReviewPanel.vue**

```vue
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
```

- [ ] **Step 2: Commit**

```bash
git add gui/src/components/ReviewPanel.vue
git commit -m "feat: add ReviewPanel for interactive supervisor interrupt review"
```

---

### Task 7: Wire everything into App.vue + build

**Files:**
- Create: `gui/src/App.vue`

- [ ] **Step 1: Create gui/src/App.vue**

```vue
<template>
  <div class="app-layout">
    <header class="app-header">
      <span class="app-title">oxidant</span>
      <span class="app-subtitle">TS → Rust translation harness</span>
    </header>

    <main class="app-main">
      <aside class="sidebar">
        <RunControls />
        <ProgressDashboard />
      </aside>
      <section class="feed-area">
        <LiveNodeFeed />
      </section>
    </main>

    <!-- Review panel overlays from the right when an interrupt fires -->
    <ReviewPanel />
  </div>
</template>

<script setup lang="ts">
import RunControls from './components/RunControls.vue'
import ProgressDashboard from './components/ProgressDashboard.vue'
import LiveNodeFeed from './components/LiveNodeFeed.vue'
import ReviewPanel from './components/ReviewPanel.vue'
</script>

<style>
.app-layout { display: flex; flex-direction: column; height: 100vh; }
.app-header {
  display: flex; align-items: baseline; gap: 12px;
  padding: 12px 20px; border-bottom: 1px solid #333; background: #0a0a0a;
}
.app-title { font-size: 18px; font-weight: bold; color: #a78bfa; }
.app-subtitle { font-size: 12px; color: #555; }
.app-main { display: flex; flex: 1; overflow: hidden; }
.sidebar { width: 340px; border-right: 1px solid #333; overflow-y: auto; flex-shrink: 0; }
.feed-area { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
</style>
```

- [ ] **Step 2: Verify TypeScript compiles cleanly**

```bash
cd gui && npx vue-tsc --noEmit
```

Expected: 0 errors

- [ ] **Step 3: Build for production**

```bash
cd gui && npm run build
```

Expected: `dist/` directory created with `index.html`, `assets/index-*.js`, `assets/index-*.css`.

- [ ] **Step 4: Verify build serves correctly**

In one terminal:
```bash
uv run oxidant serve --gui-dist gui/dist --port 8000
```

In browser, open `http://localhost:8000`. Expected: oxidant dashboard with "oxidant" header, controls panel, and empty live feed.

- [ ] **Step 5: Run all tests**

```bash
cd gui && npm test
cd /Users/ceres/Desktop/SignalCanvas/oxidant && uv run pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/ceres/Desktop/SignalCanvas/oxidant
git add gui/src/App.vue gui/dist/
git commit -m "feat: wire App.vue; add production build; gui/dist serves from oxidant serve"
```

---

## Verify end-to-end (manual)

With a real manifest available:

1. `uv run oxidant serve --gui-dist gui/dist`
2. Open `http://localhost:8000`
3. Fill in manifest path + target path, click Start
4. Watch LiveNodeFeed update as nodes translate
5. Set review_mode to `interactive`, restart run, wait for a node to exhaust opus — ReviewPanel should appear
6. Edit the supervisor hint, click Resume, watch the run continue

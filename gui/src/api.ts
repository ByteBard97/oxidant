/** Typed wrappers for the oxidant FastAPI REST endpoints. */

export interface StatsResponse {
  total: number
  converted: number
  not_started: number
  in_progress: number
  human_review: number
  failed: number
}

export interface ModuleStats {
  module: string
  total: number
  converted: number
  human_review: number
  in_progress: number
  not_started: number
  pct_complete: number
}

export interface ErrorPattern {
  pattern: string
  count: number
  node_ids: string[]
}

export interface NodePage {
  total: number
  limit: number
  offset: number
  nodes: Array<{
    node_id: string
    source_file: string
    node_kind: string
    status: string
    tier: string | null
    attempt_count: number
    last_error: string | null
  }>
}

export interface StartRunRequest {
  db_path: string
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

  getDefaults: () =>
    get<{ db_path?: string; target_path?: string; snippets_dir?: string }>('/api/defaults'),

  getStats: () =>
    get<StatsResponse>('/api/stats'),

  getModules: () =>
    get<ModuleStats[]>('/api/modules'),

  getErrors: () =>
    get<ErrorPattern[]>('/api/errors'),

  getNodes: (params: { status?: string; module?: string; limit?: number; offset?: number }) =>
    get<NodePage>(`/api/nodes?${new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]))
    )}`),
}

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

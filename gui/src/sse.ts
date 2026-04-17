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

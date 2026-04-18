import { ref } from 'vue'
import { useRunStore } from '../store'
import { useConfirm } from './useConfirm'
import { api } from '../api'
import { connectSSE, disconnectSSE } from '../sse'

/**
 * Shared run lifecycle actions used by both RunControls (sidebar) and
 * RunConfigPanel (center). Single source of truth for start / pause / abort.
 */
export function useRunActions() {
  const store         = useRunStore()
  const { confirm }   = useConfirm()
  const error         = ref('')

  async function start() {
    error.value = ''
    try {
      const res = await api.startRun({
        db_path:     store.dbPath,
        target_path: store.targetPath,
        review_mode: store.reviewMode,
        thread_id:   store.status === 'paused' ? store.threadId : null,
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
    const ok = await confirm(
      'Abort this run? State will be discarded and the run cannot be resumed.',
      'ABORT RUN',
      'ABORT',
    )
    if (!ok) return
    try {
      await api.abortRun(store.threadId)
      store.setStatus('aborted')
      disconnectSSE()
    } catch (e) {
      error.value = String(e)
    }
  }

  return { start, pause, abort, error }
}

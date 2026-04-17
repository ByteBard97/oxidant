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

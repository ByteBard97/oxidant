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

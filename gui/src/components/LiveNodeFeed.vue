<template>
  <div class="flex flex-col h-full overflow-hidden">

    <!-- Active node monitor -->
    <div class="px-4 pt-4 pb-2 border-b border-outline-variant/20 bg-surface-container flex flex-col gap-2 font-mono text-xs shrink-0 min-h-[84px]">
      <div class="text-zinc-500 text-[10px] tracking-widest">ACTIVE PROCESSING NODES</div>

      <!-- Node list scrolls independently so it never crushes the telemetry feed -->
      <div class="overflow-y-auto max-h-[160px] flex flex-col gap-2">
        <div v-if="activeNodeList.length === 0" class="text-zinc-600 text-[10px] italic">
          — no active nodes —
        </div>

        <div
          v-for="node in activeNodeList"
          :key="node.node_id"
          class="flex shrink-0 bg-surface-container-lowest"
        >
          <div class="rust-seam w-[2px] self-stretch" :class="tierBgColor(node.tier)" aria-hidden="true" />
          <div class="flex items-center justify-between p-2 flex-1">
            <div class="flex items-center gap-3">
              <span class="text-[8px] pulse-dot" :class="tierColor(node.tier)">●</span>
              <span class="text-zinc-300 truncate min-w-0 flex-1" :title="node.node_id">{{ shortId(node.node_id) }}</span>
            </div>
            <span class="bg-surface-container-highest text-zinc-400 px-2 py-0.5 text-[9px] uppercase tracking-wider">
              {{ node.tier.toUpperCase() }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Telemetry feed -->
    <div ref="logEl" class="flex-1 overflow-y-auto p-4 bg-surface-container-lowest font-mono text-[11px] leading-relaxed text-on-surface-variant">
      <div v-if="parsedEvents.length === 0" class="text-zinc-600">Awaiting events...</div>

      <div v-for="(evt, i) in parsedEvents" :key="i" class="mb-1.5">
        <span class="text-zinc-500">[{{ timestamp(evt) }}]</span>
        {{ ' ' }}
        <span :class="levelColor(evt.event)">{{ levelLabel(evt.event) }}</span>
        {{ ' ' }}
        <span class="text-zinc-300">{{ formatEvent(evt) }}</span>
      </div>

      <div v-if="store.status === 'interrupted'" class="mt-4 border-t border-dashed border-outline-variant/30 pt-2 text-zinc-500 font-bold">
        Awaiting Operator Input...
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { useRunStore } from '../store'
import { MAX_RECENT_EVENTS } from '../utils/constants'
import { shortId } from '../utils/strings'

const store = useRunStore()
const logEl = ref<HTMLElement | null>(null)

const activeNodeList = computed(() => Object.values(store.activeNodes))

const parsedEvents = computed(() => {
  return store.recentEvents.slice(0, MAX_RECENT_EVENTS).map(raw => {
    try { return JSON.parse(raw) } catch { return { event: 'unknown' } }
  })
})

watch(parsedEvents, () => {
  nextTick(() => {
    if (logEl.value) logEl.value.scrollTop = 0
  })
})


function timestamp(_evt: Record<string, unknown>): string {
  const now = new Date()
  return [
    now.getHours().toString().padStart(2, '0'),
    now.getMinutes().toString().padStart(2, '0'),
    now.getSeconds().toString().padStart(2, '0'),
  ].join(':')
}

function levelLabel(evt: string): string {
  if (['node_complete', 'run_complete'].includes(evt)) return 'INFO'
  if (['interrupt', 'error'].includes(evt)) return 'WARN'
  if (evt === 'supervisor') return 'DEBUG'
  return 'INFO'
}

function levelColor(evt: string): string {
  if (['interrupt', 'error'].includes(evt)) return 'text-primary-container'
  if (evt === 'supervisor') return 'text-zinc-400'
  return 'text-secondary'
}

function tierBgColor(tier: string): string {
  if (tier === 'opus') return 'bg-primary-container'
  return 'bg-secondary'
}

function tierColor(tier: string): string {
  if (tier === 'opus') return 'text-primary-container'
  return 'text-secondary'
}

function formatEvent(evt: Record<string, unknown>): string {
  const e = evt.event as string
  if (e === 'node_start') return `Node ${shortId(evt.node_id as string)} started [${evt.tier}]`
  if (e === 'node_complete') return `${shortId(evt.node_id as string)} converted (${evt.attempts} attempts)`
  if (e === 'node_escalate') return `${shortId(evt.node_id as string)} escalated ${evt.from_tier}→${evt.to_tier}`
  if (e === 'supervisor') return `Supervisor hint for ${shortId(evt.node_id as string)}`
  if (e === 'interrupt') return `REVIEW REQUIRED: ${shortId(evt.node_id as string)}`
  if (e === 'error') return `FAILED: ${shortId(evt.node_id as string)}`
  if (e === 'run_complete') return `Run complete — ${evt.converted} converted, ${evt.needs_review} for review`
  if (e === 'status') return evt.message as string
  return e
}
</script>

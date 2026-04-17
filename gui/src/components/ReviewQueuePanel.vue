<template>
  <div class="flex-1 flex flex-col overflow-hidden font-mono">

    <!-- Header -->
    <div class="px-4 border-b border-outline-variant/20 bg-surface-container flex items-center justify-between shrink-0 min-h-[84px]">
      <div class="flex flex-col gap-1">
        <div class="text-[10px] text-zinc-500 tracking-widest">REVIEW QUEUE</div>
        <div class="text-[11px] text-zinc-400">
          {{ queueItems.length }} node{{ queueItems.length !== 1 ? 's' : '' }} awaiting manual attention
        </div>
      </div>
      <span
        v-if="queueItems.length > 0"
        class="text-primary-container font-bold text-lg tabular-nums"
      >{{ queueItems.length }}</span>
    </div>

    <!-- Empty state -->
    <div v-if="queueItems.length === 0"
         class="flex-1 flex flex-col items-center justify-center gap-4 text-center p-8">
      <span class="material-symbols-outlined text-zinc-700 text-[48px]">task_alt</span>
      <div class="text-[11px] text-zinc-600 uppercase tracking-widest">Queue Empty</div>
      <div class="text-[10px] text-zinc-700">No nodes require manual review.</div>
    </div>

    <!-- Queue list -->
    <div v-else class="flex-1 overflow-y-auto">
      <div
        v-for="item in queueItems"
        :key="item.node_id"
        class="border-b border-outline-variant/15 flex hover:bg-surface-container/50 transition-colors"
      >
        <div class="rust-seam w-[2px] self-stretch"
             :class="item.type === 'interrupt' ? 'bg-primary-container' : 'bg-zinc-700'"
             aria-hidden="true" />
        <div class="p-4 flex flex-col gap-2 flex-1">
        <!-- Node ID + badge -->
        <div class="flex items-start justify-between gap-3">
          <span class="text-zinc-300 text-[11px] break-all min-w-0">
            {{ item.node_id }}
          </span>
          <span
            class="shrink-0 text-[9px] px-2 py-0.5 uppercase tracking-wider font-bold"
            :class="item.type === 'interrupt'
              ? 'bg-primary-container/20 text-primary-container'
              : 'bg-zinc-800 text-zinc-500'"
          >
            {{ item.type === 'interrupt' ? 'INTERRUPTED' : 'FAILED' }}
          </span>
        </div>

        <!-- Error / message -->
        <pre class="text-[10px] text-zinc-500 whitespace-pre-wrap leading-relaxed line-clamp-2">{{ item.message }}</pre>

        <!-- Timestamp -->
        <div class="text-[9px] text-zinc-700 tracking-wider">{{ item.time }}</div>
        </div><!-- end inner flex-1 -->
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRunStore } from '../store'
import { shortId } from '../utils/strings'

const store = useRunStore()

interface QueueItem {
  node_id: string
  type: 'error' | 'interrupt'
  message: string
  time: string
}

const queueItems = computed<QueueItem[]>(() => {
  const items: QueueItem[] = []
  // Walk recentEvents (newest-first) and collect failures
  ;[...store.recentEvents].reverse().forEach(raw => {
    try {
      const evt = JSON.parse(raw)
      if (evt.event === 'error') {
        items.push({
          node_id: evt.node_id,
          type:    'error',
          message: evt.message ?? 'Translation failed — all tiers exhausted',
          time:    new Date().toLocaleTimeString(),
        })
      } else if (evt.event === 'interrupt') {
        items.push({
          node_id: evt.node_id,
          type:    'interrupt',
          message: evt.payload?.error ?? 'Interrupt — operator input required',
          time:    new Date().toLocaleTimeString(),
        })
      }
    } catch (e) { console.warn('ReviewQueuePanel: failed to parse event', raw, e) }
  })
  return items
})

</script>

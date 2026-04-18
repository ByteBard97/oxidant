<template>
  <div class="flex flex-col gap-3">
    <div class="text-[10px] text-zinc-500 tracking-widest border-b border-dashed border-outline-variant/30 pb-2 flex justify-between">
      <span>ERROR PATTERNS</span>
      <span class="text-zinc-600">{{ patterns.length }} distinct patterns</span>
    </div>

    <div v-if="error" class="text-error text-[10px] font-mono">{{ error }}</div>

    <div v-if="patterns.length === 0 && !error" class="text-zinc-600 text-[10px] font-mono py-4 text-center">
      No errors — all nodes converted successfully
    </div>

    <div class="flex flex-col gap-px max-h-[380px] overflow-y-auto">
      <div
        v-for="p in patterns"
        :key="p.pattern"
        class="flex flex-col gap-1 px-2 py-2 hover:bg-surface-container cursor-pointer transition-colors"
        @click="expanded = expanded === p.pattern ? null : p.pattern"
      >
        <!-- Error summary row -->
        <div class="flex items-start gap-2">
          <!-- Count bar -->
          <div class="flex items-center gap-1.5 shrink-0 w-12">
            <span class="text-primary-container font-bold font-mono text-[11px] tabular-nums">{{ p.count }}</span>
          </div>
          <!-- Inline bar -->
          <div class="h-1.5 self-center flex-1 bg-surface-container-high overflow-hidden">
            <div
              class="h-full bg-primary-container/60"
              :style="{ width: Math.min(100, 100 * p.count / maxCount) + '%' }"
            />
          </div>
        </div>
        <!-- Pattern text -->
        <div class="text-[9px] font-mono text-zinc-400 leading-relaxed ml-14 line-clamp-2">
          {{ cleanPattern(p.pattern) }}
        </div>

        <!-- Expanded: node IDs -->
        <div v-if="expanded === p.pattern" class="ml-14 mt-1 flex flex-col gap-0.5">
          <div
            v-for="nid in p.node_ids"
            :key="nid"
            class="text-[9px] font-mono text-zinc-500 hover:text-zinc-300 transition-colors truncate"
            :title="nid"
          >
            ↳ {{ nid }}
          </div>
          <div v-if="p.count > p.node_ids.length" class="text-[9px] text-zinc-600 font-mono">
            +{{ p.count - p.node_ids.length }} more
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, type ErrorPattern } from '../api'
import { useRunStore } from '../store'

const store = useRunStore()
const patterns = ref<ErrorPattern[]>([])
const error = ref('')
const expanded = ref<string | null>(null)

const maxCount = computed(() =>
  patterns.value.reduce((m, p) => Math.max(m, p.count), 1)
)

function cleanPattern(raw: string): string {
  // Show first meaningful line of the pattern
  return raw.split('\n').find(l => l.trim().length > 0) || raw
}

async function refresh() {
  try {
    patterns.value = await api.getErrors()
    error.value = ''
  } catch (e) {
    error.value = String(e)
  }
}

let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  refresh()
  // Poll every 30s — errors don't change as fast as module progress
  timer = setInterval(() => {
    if (store.status === 'running' || store.status === 'idle') refresh()
  }, 30000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

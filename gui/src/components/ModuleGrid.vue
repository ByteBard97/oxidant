<template>
  <div class="flex flex-col gap-3">
    <div class="text-[10px] text-zinc-500 tracking-widest border-b border-dashed border-outline-variant/30 pb-2 flex justify-between">
      <span>MODULE PROGRESS</span>
      <span class="text-zinc-600">{{ modules.length }} modules</span>
    </div>

    <div v-if="error" class="text-error text-[10px] font-mono">{{ error }}</div>

    <div v-if="modules.length === 0 && !error" class="text-zinc-600 text-[10px] font-mono py-4 text-center">
      No data — run import-manifest and start Phase B
    </div>

    <!-- Filter bar -->
    <div v-if="modules.length > 0" class="flex gap-2">
      <input
        v-model="filter"
        class="flex-1 bg-surface-container-lowest border-l-2 border-transparent focus:border-primary outline-none text-[11px] font-mono text-zinc-300 px-2 py-1 placeholder-zinc-600"
        placeholder="filter by module name..."
      />
      <select
        v-model="sortBy"
        class="bg-surface-container-lowest text-[10px] font-mono text-zinc-400 px-2 py-1 outline-none border-0"
      >
        <option value="pct_desc">% done ↓</option>
        <option value="pct_asc">% done ↑</option>
        <option value="review">review ↓</option>
        <option value="name">name</option>
      </select>
    </div>

    <!-- Module rows -->
    <div class="flex flex-col gap-1 max-h-[420px] overflow-y-auto pr-1">
      <div
        v-for="m in filteredModules"
        :key="m.module"
        class="flex flex-col gap-1 group cursor-pointer hover:bg-surface-container px-2 py-1.5 transition-colors"
        @click="selectedModule = selectedModule === m.module ? null : m.module"
        :class="selectedModule === m.module ? 'bg-surface-container' : ''"
      >
        <!-- Module name + counters -->
        <div class="flex items-center gap-2 text-[10px] font-mono">
          <span class="flex-1 text-zinc-300 truncate" :title="m.module">
            {{ shortName(m.module) }}
          </span>
          <span class="text-secondary font-bold tabular-nums">{{ m.converted }}/{{ m.total }}</span>
          <span v-if="m.human_review > 0" class="text-primary-container font-bold tabular-nums">
            {{ m.human_review }}⚑
          </span>
          <span class="text-zinc-500 tabular-nums w-8 text-right">{{ m.pct_complete }}%</span>
        </div>

        <!-- Progress bar -->
        <div class="h-1.5 w-full bg-surface-container-high flex gap-px overflow-hidden">
          <div
            class="h-full bg-secondary/80 transition-all duration-500"
            :style="{ width: (m.pct_complete) + '%' }"
          />
          <div
            v-if="m.human_review > 0"
            class="h-full bg-primary-container/70 transition-all duration-500"
            :style="{ width: (100 * m.human_review / m.total) + '%' }"
          />
          <div
            v-if="m.in_progress > 0"
            class="h-full bg-tertiary/70 transition-all duration-500"
            :style="{ width: (100 * m.in_progress / m.total) + '%' }"
          />
        </div>
      </div>
    </div>

    <!-- Legend -->
    <div class="flex gap-4 text-[9px] font-mono text-zinc-600 pt-1">
      <span class="flex items-center gap-1"><span class="w-2 h-2 bg-secondary/80 inline-block"></span> converted</span>
      <span class="flex items-center gap-1"><span class="w-2 h-2 bg-primary-container/70 inline-block"></span> review</span>
      <span class="flex items-center gap-1"><span class="w-2 h-2 bg-tertiary/70 inline-block"></span> active</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, type ModuleStats } from '../api'
import { useRunStore } from '../store'

const store = useRunStore()
const modules = ref<ModuleStats[]>([])
const error = ref('')
const filter = ref('')
const sortBy = ref<'pct_desc' | 'pct_asc' | 'review' | 'name'>('pct_desc')
const selectedModule = ref<string | null>(null)

function shortName(path: string): string {
  const parts = path.split('/')
  return parts[parts.length - 1] || path
}

const filteredModules = computed(() => {
  let list = modules.value
  if (filter.value) {
    const q = filter.value.toLowerCase()
    list = list.filter(m => m.module.toLowerCase().includes(q))
  }
  return [...list].sort((a, b) => {
    if (sortBy.value === 'pct_desc') return b.pct_complete - a.pct_complete
    if (sortBy.value === 'pct_asc') return a.pct_complete - b.pct_complete
    if (sortBy.value === 'review') return b.human_review - a.human_review
    return a.module.localeCompare(b.module)
  })
})

async function refresh() {
  try {
    modules.value = await api.getModules()
    error.value = ''
  } catch (e) {
    error.value = String(e)
  }
}

let timer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  refresh()
  // Poll every 5s while running, every 30s otherwise
  timer = setInterval(() => {
    if (store.status === 'running' || store.status === 'idle') refresh()
  }, 5000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

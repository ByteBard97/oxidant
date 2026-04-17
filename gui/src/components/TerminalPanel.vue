<template>
  <!-- Drag handle — sits at the very top, above the header -->
  <div
    class="flex flex-col bg-surface-container-lowest border-t border-outline-variant/20 font-mono"
    :style="{ height: height + 'px' }"
  >
    <div
      class="h-[10px] flex items-center justify-center cursor-row-resize shrink-0 select-none"
      @mousedown="$emit('dragstart', $event)"
    >
      <div class="h-1 self-stretch w-full bg-outline-variant/30 rust-seam" />
    </div>

    <!-- Header -->
    <div class="flex items-center justify-between px-3 py-1.5 bg-surface-container shrink-0 border-b border-outline-variant/20">
      <span class="text-[10px] tracking-widest text-zinc-500 uppercase">Supervisor Shell</span>
      <button
        class="text-zinc-500 hover:text-primary-container text-sm leading-none transition-colors"
        @click="$emit('close')"
        aria-label="Close terminal"
      >✕</button>
    </div>

    <!-- Output area -->
    <div
      ref="logEl"
      class="flex-1 overflow-y-auto p-3 font-mono text-[11px] leading-relaxed"
    >
      <div v-for="(line, i) in lines" :key="i" class="mb-0.5">
        <template v-if="line.type === 'input'">
          <span class="text-outline-variant">oxidant:~$&nbsp;</span>
          <span class="text-zinc-300">{{ line.text }}</span>
        </template>
        <template v-else>
          <span class="text-secondary">{{ line.text }}</span>
        </template>
      </div>
    </div>

    <!-- Input row -->
    <div class="flex items-center gap-1 px-3 py-2 border-t border-outline-variant/20 shrink-0">
      <span class="text-outline-variant text-[11px] font-mono shrink-0">oxidant:~$</span>
      <input
        v-model="inputText"
        type="text"
        class="bg-transparent border-none outline-none text-secondary flex-1 font-mono text-[11px]"
        spellcheck="false"
        autocomplete="off"
        @keydown.enter="submit"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { useRunStore } from '../store'

defineProps<{ height: number }>()
defineEmits<{
  close: []
  dragstart: [e: MouseEvent]
}>()

const store = useRunStore()
const logEl = ref<HTMLElement | null>(null)
const inputText = ref('')

interface LogLine {
  type: 'input' | 'output'
  text: string
}

const lines = ref<LogLine[]>([])

// ── Command processor ─────────────────────────────────────────────────────────

const COMMANDS: Record<string, () => string> = {
  help: () => 'Available: status, workers, clear, help',
  status: () =>
    `● ${store.status.toUpperCase()} — ${store.stats.converted} converted, ${store.stats.inProgress} in-progress, ${store.stats.needsReview} for review`,
  workers: () => 'WORKERS: 4/4 active  [sonnet×3, opus×1]',
  clear: () => '__CLEAR__',
}

function runCommand(cmd: string): string {
  const fn = COMMANDS[cmd.trim().toLowerCase()]
  if (!fn) return `command not found: ${cmd} — type 'help' for available commands`
  return fn()
}

function submit() {
  const cmd = inputText.value.trim()
  if (!cmd) return
  inputText.value = ''

  lines.value.push({ type: 'input', text: cmd })

  const result = runCommand(cmd)
  if (result === '__CLEAR__') {
    lines.value = []
  } else {
    lines.value.push({ type: 'output', text: result })
  }

  nextTick(() => {
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
  })
}

// ── Welcome message ───────────────────────────────────────────────────────────

onMounted(() => {
  lines.value.push({ type: 'output', text: "● supervisor shell — type 'help' for commands" })
})
</script>

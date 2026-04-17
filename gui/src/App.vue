<template>
  <div class="h-screen flex flex-col bg-[#121416] text-on-surface font-body overflow-hidden">

    <!-- Top nav bar -->
    <header class="bg-[#1A1C1E] flex justify-between items-center w-full px-4 h-12 border-b border-[#2D2F31] shrink-0 font-mono text-sm tracking-tighter uppercase relative z-50">
      <Tooltip content="Live translation event stream" position="bottom">
        <span class="font-black text-xl text-primary-container tracking-widest cursor-default">[TERMINAL.LOGS]</span>
      </Tooltip>
      <div class="flex items-center gap-4">
        <Tooltip content="SSE stream status — backend supervisor reachable" position="bottom">
          <div class="flex items-center gap-2 text-secondary bg-secondary/10 px-3 py-1 border border-secondary/30 text-xs cursor-default">
            <span class="text-[8px] pulse-dot">●</span>
            <span>CONNECTED</span>
          </div>
        </Tooltip>
        <div class="flex items-center gap-2">
          <Tooltip content="Memory usage — active node contexts" position="bottom">
            <button @click="memoryModal.open()" class="text-zinc-500 hover:text-white transition-colors p-1">
              <span class="material-symbols-outlined text-[20px]">memory</span>
            </button>
          </Tooltip>
          <Tooltip content="System health — worker + GPU sensors" position="bottom">
            <button @click="sensorsModal.open()" class="text-zinc-500 hover:text-white transition-colors p-1">
              <span class="material-symbols-outlined text-[20px]">sensors</span>
            </button>
          </Tooltip>
          <Tooltip content="Supervisor shell" position="bottom">
            <button @click="terminalOpen = !terminalOpen" class="transition-colors p-1"
                    :class="terminalOpen ? 'text-secondary' : 'text-zinc-500 hover:text-white'">
              <span class="material-symbols-outlined text-[20px]">terminal</span>
            </button>
          </Tooltip>
          <!-- Option B: review panel toggle button in header -->
          <Tooltip content="Toggle review panel" position="bottom">
            <button @click="reviewOpen = !reviewOpen" class="transition-colors p-1"
                    :class="reviewOpen ? 'text-secondary' : 'text-zinc-500 hover:text-white'">
              <span class="material-symbols-outlined text-[20px]">dock_to_right</span>
            </button>
          </Tooltip>
          <Tooltip content="[DEV] Seed UI with mock pipeline data" position="bottom">
            <button
              @click="seedMockData()"
              class="text-zinc-600 hover:text-tertiary transition-colors p-1 border-l border-dashed border-outline-variant/30 pl-2 ml-1"
            >
              <span class="material-symbols-outlined text-[20px]">science</span>
            </button>
          </Tooltip>
        </div>
      </div>
    </header>

    <!-- Body -->
    <div class="flex flex-1 overflow-hidden">

      <!-- Left sidebar nav -->
      <nav class="bg-[#1A1C1E] w-64 flex flex-col border-r border-[#2D2F31] shrink-0 h-full z-40 overflow-y-auto font-mono text-xs uppercase relative">
        <!-- Logo panel: rust-stained backlit surface -->
        <div class="relative h-[84px] shrink-0 border-b border-[#2D2F31] flex items-center justify-center px-4 overflow-hidden"
             style="background: radial-gradient(ellipse at 55% 60%, #2a1a0a 0%, #0e0c0a 70%);">
          <div class="absolute inset-0 opacity-20 mix-blend-overlay pointer-events-none"
               style="background-image: url('/rust-texture.png'); background-size: 300px 300px;"></div>
          <div class="absolute inset-0 pointer-events-none"
               style="background: radial-gradient(ellipse at 50% 55%, #ff990020 0%, transparent 70%);"></div>
          <div class="neon-logo-wrap w-36 relative z-10" :style="{ opacity: neonOpacity }">
            <img src="/oxidant-logo.svg" alt="OXIDANT" class="w-full h-auto neon-logo" />
          </div>
        </div>

        <!-- Sidebar right-border seam -->
        <div class="rust-seam rust-seam-overlay" aria-hidden="true" />

        <!-- Nav links — active indicator is a dedicated .rust-seam strip, not a CSS border -->
        <div class="flex flex-col py-2">
          <Tooltip content="Configure paths, mode, and start/stop the run" position="right">
            <a class="relative text-zinc-500 py-3 px-4 flex items-center gap-3 hover:bg-zinc-800 transition-all cursor-pointer"
               :class="activeTab === 'run' && 'bg-secondary/10 text-secondary'"
               @click="activeTab = 'run'">
              <div v-if="activeTab === 'run'" class="rust-seam absolute right-0 inset-y-0 w-[4px] bg-secondary" aria-hidden="true" />
              <span class="material-symbols-outlined text-[18px]">play_arrow</span>
              [RUN_CONTROLS]
            </a>
          </Tooltip>
          <Tooltip content="Live SSE telemetry feed — node events as they happen" position="right">
            <a class="relative text-zinc-500 py-3 px-4 flex items-center gap-3 hover:bg-zinc-800 transition-all cursor-pointer"
               :class="activeTab === 'logs' && 'bg-secondary/10 text-secondary'"
               @click="activeTab = 'logs'">
              <div v-if="activeTab === 'logs'" class="rust-seam absolute right-0 inset-y-0 w-[4px] bg-secondary" aria-hidden="true" />
              <span class="material-symbols-outlined text-[18px]">analytics</span>
              [CONV_LOGS]
            </a>
          </Tooltip>
          <Tooltip content="Nodes that failed auto-translation and need human review" position="right">
            <a class="relative text-zinc-500 py-3 px-4 flex items-center gap-3 hover:bg-zinc-800 transition-all cursor-pointer"
               :class="activeTab === 'review' && 'bg-secondary/10 text-secondary'"
               @click="activeTab = 'review'">
              <div v-if="activeTab === 'review'" class="rust-seam absolute right-0 inset-y-0 w-[4px] bg-secondary" aria-hidden="true" />
              <span class="material-symbols-outlined text-[18px]">checklist</span>
              [REV_QUEUE]
              <span v-if="store.stats.needsReview > 0" class="ml-auto text-primary-container font-bold">{{ store.stats.needsReview }}</span>
            </a>
          </Tooltip>
        </div>

        <!-- Bottom: run controls + telemetry -->
        <div class="mt-auto border-t border-[#2D2F31] p-4 flex flex-col gap-4">
          <RunControls />
          <ProgressDashboard />
        </div>
      </nav>

      <!-- Main workspace -->
      <main class="flex-1 bg-surface-container-low flex flex-col overflow-hidden">

        <!-- Top row: center + resize handle + review panel -->
        <div class="flex flex-1 min-h-0 overflow-hidden">

          <!-- Center column -->
          <div class="flex-1 flex flex-col min-w-0 overflow-hidden">
            <RunConfigPanel   v-if="activeTab === 'run'" />
            <ReviewQueuePanel v-else-if="activeTab === 'review'" />
            <LiveNodeFeed     v-else />
          </div>

          <!-- Drag handle + review panel (hidden together when closed) -->
          <template v-if="reviewOpen">
            <!-- Drag handle — accent colour tracks review state -->
            <div class="resize-handle shrink-0" @mousedown="startReviewDrag" title="Drag to resize panels">
              <div class="resize-handle-dashes" />
              <div class="rust-seam resize-handle-accent"
                   :class="store.pendingReview ? 'bg-primary-container' : 'bg-outline-variant/30'" />
            </div>

            <!-- Review panel — width driven by drag; scrolls as one unit -->
            <div class="shrink-0 overflow-y-auto overflow-x-hidden" :style="{ width: reviewWidth + 'px' }">
              <ReviewPanel />
            </div>
          </template>

          <!-- Option A: collapsed tab at right edge when review is closed -->
          <div
            v-else
            class="w-7 shrink-0 bg-surface-container flex flex-col items-center justify-center cursor-pointer hover:bg-surface-container-high transition-colors border-l border-outline-variant/20"
            @click="reviewOpen = true"
            title="Open review panel"
          >
            <span class="text-zinc-600 hover:text-zinc-400 text-[8px] font-mono uppercase tracking-widest select-none"
                  style="writing-mode: vertical-rl; transform: rotate(180deg)">
              ⟨⟨ REVIEW
            </span>
          </div>

        </div>

        <!-- Terminal panel — slides up from bottom, respects review panel width -->
        <TerminalPanel
          v-if="terminalOpen"
          :height="terminalHeight"
          @close="terminalOpen = false"
          @dragstart="startTerminalDrag"
        />

      </main>
    </div>

    <ConfirmModal />
    <MemoryModal />
    <SensorsModal />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRunStore } from './store'
import { useNeonFlicker } from './composables/useNeonFlicker'
import { useResize } from './composables/useResize'
import { useMemoryModal } from './composables/useMemoryModal'
import { useSensorsModal } from './composables/useSensorsModal'
import { seedMockData } from './composables/useMockData'
import Tooltip from './components/Tooltip.vue'
import RunControls from './components/RunControls.vue'
import ProgressDashboard from './components/ProgressDashboard.vue'
import LiveNodeFeed from './components/LiveNodeFeed.vue'
import RunConfigPanel from './components/RunConfigPanel.vue'
import ReviewQueuePanel from './components/ReviewQueuePanel.vue'
import ReviewPanel from './components/ReviewPanel.vue'
import ConfirmModal from './components/ConfirmModal.vue'
import MemoryModal from './components/MemoryModal.vue'
import SensorsModal from './components/SensorsModal.vue'
import TerminalPanel from './components/TerminalPanel.vue'

const store = useRunStore()
const activeTab = ref<'run' | 'logs' | 'review'>('logs')
const { opacity: neonOpacity } = useNeonFlicker()

// Review panel — horizontal resize + open/close toggle
const { width: reviewWidth, startDrag: startReviewDrag } = useResize(450)
const reviewOpen = ref(true)

// Terminal panel — vertical resize + open/close toggle
const { size: terminalHeight, startDrag: startTerminalDrag } = useResize(260, { min: 120, max: 600, axis: 'y' })
const terminalOpen = ref(false)

const memoryModal = useMemoryModal()
const sensorsModal = useSensorsModal()
</script>

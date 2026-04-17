<template>
  <div class="h-screen flex flex-col bg-[#121416] text-on-surface font-body overflow-hidden">

    <!-- Top nav bar -->
    <header class="bg-[#1A1C1E] flex justify-between items-center w-full px-4 h-12 border-b border-[#2D2F31] shrink-0 font-mono text-sm tracking-tighter uppercase relative z-50">
      <span class="font-black text-xl text-primary-container tracking-widest">[TERMINAL.LOGS]</span>
      <div class="flex items-center gap-4">
        <div class="flex items-center gap-2 text-secondary bg-secondary/10 px-3 py-1 border border-secondary/30 text-xs">
          <span class="text-[8px] pulse-dot">●</span>
          <span>CONNECTED</span>
        </div>
        <div class="flex items-center gap-2">
          <button class="text-zinc-500 hover:text-white transition-colors p-1">
            <span class="material-symbols-outlined text-[20px]">memory</span>
          </button>
          <button class="text-zinc-500 hover:text-white transition-colors p-1">
            <span class="material-symbols-outlined text-[20px]">sensors</span>
          </button>
          <button class="text-zinc-500 hover:text-white transition-colors p-1">
            <span class="material-symbols-outlined text-[20px]">terminal</span>
          </button>
        </div>
      </div>
    </header>

    <!-- Body -->
    <div class="flex flex-1 overflow-hidden">

      <!-- Left sidebar nav -->
      <nav class="bg-[#1A1C1E] w-64 flex flex-col border-r border-[#2D2F31] shrink-0 h-full z-40 overflow-y-auto font-mono text-xs uppercase">
        <!-- Logo panel: rust-stained backlit surface -->
        <div class="relative p-5 border-b border-[#2D2F31] flex items-center justify-center overflow-hidden"
             style="background: radial-gradient(ellipse at 55% 60%, #2a1a0a 0%, #0e0c0a 70%);">
          <!-- rust bleed layer -->
          <div class="absolute inset-0 opacity-20 mix-blend-overlay pointer-events-none"
               style="background-image: url('/rust-texture.png'); background-size: 300px 300px;"></div>
          <!-- amber backlight bloom -->
          <div class="absolute inset-0 pointer-events-none"
               style="background: radial-gradient(ellipse at 50% 55%, #ff990020 0%, transparent 70%);"></div>
          <div class="neon-logo-wrap w-44 relative z-10" :style="{ opacity: neonOpacity }">
            <img src="/oxidant-logo.svg" alt="OXIDANT" class="w-full h-auto neon-logo" />
          </div>
        </div>

        <!-- Nav links -->
        <div class="flex flex-col py-2">
          <a class="text-zinc-500 py-3 px-4 flex items-center gap-3 hover:bg-zinc-800 transition-all cursor-pointer"
             :class="activeTab === 'run' && 'bg-secondary/10 text-secondary border-r-4 border-secondary'"
             @click="activeTab = 'run'">
            <span class="material-symbols-outlined text-[18px]">play_arrow</span>
            [RUN_CONTROLS]
          </a>
          <a class="text-zinc-500 py-3 px-4 flex items-center gap-3 hover:bg-zinc-800 transition-all cursor-pointer"
             :class="activeTab === 'logs' && 'bg-secondary/10 text-secondary border-r-4 border-secondary'"
             @click="activeTab = 'logs'">
            <span class="material-symbols-outlined text-[18px]">analytics</span>
            [CONV_LOGS]
          </a>
          <a class="text-zinc-500 py-3 px-4 flex items-center gap-3 hover:bg-zinc-800 transition-all cursor-pointer"
             :class="activeTab === 'review' && 'bg-secondary/10 text-secondary border-r-4 border-secondary'"
             @click="activeTab = 'review'">
            <span class="material-symbols-outlined text-[18px]">checklist</span>
            [REV_QUEUE]
            <span v-if="store.stats.needsReview > 0" class="ml-auto text-primary-container font-bold">{{ store.stats.needsReview }}</span>
          </a>
        </div>

        <!-- Bottom: run controls + telemetry -->
        <div class="mt-auto border-t border-[#2D2F31] p-4 flex flex-col gap-4">
          <RunControls />
          <ProgressDashboard />
        </div>
      </nav>

      <!-- Main workspace -->
      <main class="flex-1 bg-surface-container-low flex flex-row overflow-hidden">

        <!-- Center feed -->
        <div class="flex-1 flex flex-col min-w-0 border-r border-dashed border-[#2D2F31]">
          <LiveNodeFeed />
        </div>

        <!-- Review panel — always visible third column -->
        <ReviewPanel />

      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRunStore } from './store'
import { useNeonFlicker } from './composables/useNeonFlicker'
import RunControls from './components/RunControls.vue'
import ProgressDashboard from './components/ProgressDashboard.vue'
import LiveNodeFeed from './components/LiveNodeFeed.vue'
import ReviewPanel from './components/ReviewPanel.vue'

const store = useRunStore()
const activeTab = ref<'run' | 'logs' | 'review'>('logs')
const { opacity: neonOpacity } = useNeonFlicker()
</script>

<template>
  <div class="flex flex-col gap-2 bg-surface-container-lowest p-3 border border-outline-variant/30">
    <div class="text-[10px] text-zinc-500 mb-1 tracking-widest">SESSION TELEMETRY</div>

    <!-- Segmented LED progress bar -->
    <Tooltip content="Translation progress — each segment = 10% of total nodes processed" position="right">
      <div class="flex gap-[3px] h-3 w-full mb-1 cursor-default">
        <div
          v-for="i in totalSegments"
          :key="i"
          class="flex-1 led-segment"
          :class="i <= filledSegments ? 'led-on' : 'led-off'"
          :style="i <= filledSegments ? segmentStyle(i) : {}"
        ></div>
      </div>
    </Tooltip>

    <Tooltip content="Nodes successfully translated to Rust and written to disk" position="right">
      <div class="flex justify-between items-center text-[10px] font-mono cursor-default">
        <span class="text-zinc-400">CONVERTED</span>
        <span class="text-secondary font-bold">{{ store.stats.converted.toLocaleString() }}</span>
      </div>
    </Tooltip>
    <Tooltip content="Nodes currently being processed by an LLM tier" position="right">
      <div class="flex justify-between items-center text-[10px] font-mono cursor-default">
        <span class="text-zinc-400">IN PROGRESS</span>
        <span class="text-white">{{ store.stats.inProgress }}</span>
      </div>
    </Tooltip>
    <Tooltip content="Nodes that failed all tiers and are waiting for operator review" position="right">
      <div class="flex justify-between items-center text-[10px] font-mono cursor-default">
        <span class="text-zinc-400">NEEDS REVIEW</span>
        <span class="text-primary-container">{{ store.stats.needsReview }}</span>
      </div>
    </Tooltip>

    <Tooltip :content="statusDescription" position="right">
      <div class="mt-1 text-[10px] font-mono font-bold tracking-widest cursor-default"
           :class="statusColor">
        [{{ store.status.toUpperCase() }}]
      </div>
    </Tooltip>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRunStore } from '../store'
import Tooltip from './Tooltip.vue'

const store = useRunStore()

const totalSegments = 10
const filledSegments = computed(() => {
  const total = store.stats.converted + store.stats.needsReview + store.stats.inProgress
  if (total === 0) return 0
  return Math.round((store.stats.converted / total) * totalSegments)
})

// Spread animation phases using golden ratio so segments never sync up
const PHI = 0.6180339887

function segmentStyle(i: number): Record<string, string> {
  const phase      = ((i - 1) * PHI) % 1        // 0..1, maximally spread
  const breatheDur = 2.0 + (i % 4) * 0.35       // 2.0, 2.35, 2.7, 3.05 cycling
  const faultDur   = 3.5 + (i % 7) * 0.55       // 3.5 – 6.8, 7 distinct values
  const breatheOff = -(phase * breatheDur).toFixed(2)
  const faultOff   = -(phase * faultDur).toFixed(2)
  return {
    animationDuration: `${breatheDur}s, ${faultDur}s`,
    animationDelay:    `${breatheOff}s, ${faultOff}s`,
  }
}

const statusColor = computed(() => {
  switch (store.status) {
    case 'running':     return 'text-secondary'
    case 'complete':    return 'text-secondary'
    case 'interrupted': return 'text-primary-container'
    case 'aborted':     return 'text-error'
    case 'paused':      return 'text-tertiary'
    default:            return 'text-zinc-500'
  }
})

const statusDescription = computed(() => {
  switch (store.status) {
    case 'idle':        return 'No run active — configure paths and initiate sequence'
    case 'running':     return 'Translation pipeline active — nodes being processed'
    case 'paused':      return 'Run paused — LangGraph checkpoint saved, resume any time'
    case 'interrupted': return 'Halted — a node needs operator input before continuing'
    case 'complete':    return 'Run finished — all nodes processed'
    case 'aborted':     return 'Run aborted — state discarded, cannot be resumed'
    case 'error':       return 'Unrecoverable error — check server logs'
    default:            return store.status
  }
})
</script>

<style>
.led-segment {
  position: relative;
}

.led-off {
  background: #1b2927;  /* dim: barely-visible ghost of the teal */
}

.led-on {
  background: #94d2c7;
  animation:
    led-breathe 2s ease-in-out infinite,   /* duration overridden per-segment via style */
    led-fault   3.5s steps(1, end) infinite;
}

@keyframes led-breathe {
  0%, 100% {
    background: #94d2c7;
    box-shadow:
      0 0  3px #94d2c7,
      0 0  8px rgba(148,210,199,0.70),
      0 0 16px rgba(148,210,199,0.35),
      0 0 28px rgba(148,210,199,0.15);
  }
  50% {
    background: #b2e8e0;
    box-shadow:
      0 0  5px #b2e8e0,
      0 0 14px rgba(148,210,199,0.90),
      0 0 26px rgba(148,210,199,0.55),
      0 0 44px rgba(148,210,199,0.28),
      0 0 64px rgba(148,210,199,0.10);
  }
}

/* Independent fault flicker — same snap-cut technique as the tooltip */
@keyframes led-fault {
  0%   { filter: brightness(1);    }
  8%   { filter: brightness(0.05); }
  9%   { filter: brightness(1.7);  }
  10%  { filter: brightness(0.1);  }
  11%  { filter: brightness(1.3);  }
  12%  { filter: brightness(1);    }
  50%  { filter: brightness(1);    }
  51%  { filter: brightness(0.07); }
  52%  { filter: brightness(1.5);  }
  53%  { filter: brightness(1);    }
  78%  { filter: brightness(1);    }
  79%  { filter: brightness(0.04); }
  80%  { filter: brightness(1.8);  }
  81%  { filter: brightness(0.08); }
  82%  { filter: brightness(1.2);  }
  83%  { filter: brightness(1);    }
  100% { filter: brightness(1);    }
}
</style>

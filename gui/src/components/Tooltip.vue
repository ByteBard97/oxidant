<template>
  <div class="tooltip-host" @mouseenter="show" @mouseleave="hide" @focusin="show" @focusout="hide">
    <slot />
    <Teleport to="body">
      <div
        v-if="visible"
        ref="boxEl"
        class="tooltip-box font-mono text-[10px] uppercase tracking-widest"
        :style="computedStyle"
        role="tooltip"
      >{{ content }}</div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'

const props = withDefaults(defineProps<{
  content: string
  position?: 'top' | 'bottom' | 'left' | 'right'
  delay?: number
}>(), {
  position: 'top',
  delay: 280,
})

const visible    = ref(false)
const positioned = ref(false)
const boxStyle   = ref<Record<string, string>>({})
const boxEl      = ref<HTMLElement | null>(null)
let showTimer: ReturnType<typeof setTimeout> | null = null
let hostEl: HTMLElement | null = null

// Keep tooltip invisible until coordinates are set to prevent the 1-frame flash
const computedStyle = computed(() => ({
  ...boxStyle.value,
  opacity:    positioned.value ? '1' : '0',
  transition: positioned.value ? 'opacity 80ms ease-out' : 'none',
}))

function show(e: MouseEvent | FocusEvent) {
  const wrapper = e.currentTarget as HTMLElement
  // display:contents has no layout box — measure the actual slotted child
  hostEl = (wrapper.firstElementChild as HTMLElement) ?? wrapper
  if (showTimer) clearTimeout(showTimer)
  showTimer = setTimeout(async () => {
    positioned.value = false
    visible.value    = true
    await nextTick()
    calcPosition()
    requestAnimationFrame(() => { positioned.value = true })
  }, props.delay)
}

function hide() {
  if (showTimer) clearTimeout(showTimer)
  visible.value    = false
  positioned.value = false
}

function calcPosition() {
  if (!hostEl || !boxEl.value) return

  const anchor  = hostEl.getBoundingClientRect()
  const box     = boxEl.value.getBoundingClientRect()
  const gap     = 10   // px between anchor and tooltip
  const margin  = 8    // min px from viewport edge
  const vw      = window.innerWidth
  const vh      = window.innerHeight

  // Compute unclamped top/left as absolute pixel coords (no CSS transforms)
  let top: number
  let left: number

  switch (props.position) {
    case 'bottom':
      top  = anchor.bottom + gap
      left = anchor.left + anchor.width / 2 - box.width / 2
      break
    case 'left':
      top  = anchor.top + anchor.height / 2 - box.height / 2
      left = anchor.left - box.width - gap
      break
    case 'right':
      top  = anchor.top + anchor.height / 2 - box.height / 2
      left = anchor.right + gap
      break
    default: // top
      top  = anchor.top - box.height - gap
      left = anchor.left + anchor.width / 2 - box.width / 2
  }

  // Clamp so the tooltip never escapes the viewport
  left = Math.max(margin, Math.min(left, vw - box.width  - margin))
  top  = Math.max(margin, Math.min(top,  vh - box.height - margin))

  boxStyle.value = {
    position: 'fixed',
    zIndex:   '99999',
    top:      `${top}px`,
    left:     `${left}px`,
  }
}
</script>

<style scoped>
.tooltip-host {
  display: contents;
}
</style>

<style>
.tooltip-box {
  position: fixed;
  background: #1e2022;
  color: #ffb59d;
  border: 1px dashed #57423b;
  border-left: 2px solid #ffb59d;
  padding: 5px 10px;
  white-space: nowrap;
  pointer-events: none;
  box-shadow: 0 4px 16px rgba(0,0,0,0.7);
  animation:
    tooltip-breathe 3.4s ease-in-out infinite,
    tooltip-fault   3.2s steps(1, end) infinite;
}

@keyframes tooltip-breathe {
  0%, 100% {
    text-shadow:
      0 0  4px rgba(255,181,157,0.95),
      0 0 10px rgba(255,181,157,0.60),
      0 0 22px rgba(255,181,157,0.25),
      0 0 40px rgba(255,181,157,0.10);
  }
  50% {
    text-shadow:
      0 0  6px rgba(255,181,157,1.00),
      0 0 16px rgba(255,181,157,0.75),
      0 0 36px rgba(255,181,157,0.40),
      0 0 64px rgba(255,181,157,0.20),
      0 0 90px rgba(255,181,157,0.07);
  }
}

@keyframes tooltip-fault {
  0%   { filter: brightness(1);    }
  10%  { filter: brightness(0.06); }
  11%  { filter: brightness(1.6);  }
  12%  { filter: brightness(0.08); }
  13%  { filter: brightness(1.3);  }
  14%  { filter: brightness(1);    }
  40%  { filter: brightness(1);    }
  41%  { filter: brightness(0.04); }
  42%  { filter: brightness(1.5);  }
  43%  { filter: brightness(1);    }
  68%  { filter: brightness(1);    }
  69%  { filter: brightness(0.05); }
  70%  { filter: brightness(1.7);  }
  71%  { filter: brightness(0.1);  }
  72%  { filter: brightness(1.4);  }
  73%  { filter: brightness(0.05); }
  74%  { filter: brightness(1.2);  }
  75%  { filter: brightness(1);    }
  100% { filter: brightness(1);    }
}
</style>

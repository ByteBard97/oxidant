# Oxidant GUI — Panels & Modals Spec

**Date:** 2026-04-17  
**Status:** Ready for implementation  
**Branch to compare against:** `geoff/gui-polish-apr17`

This spec describes four interactive surface additions to the Oxidant GUI. All four live in `gui/src/`. The existing codebase already has the layout shell (`App.vue`), Pinia store (`store.ts`), and Tailwind config. These features layer on top.

---

## 1. Review Panel Toggle

The right-hand `ReviewPanel` can be opened and closed without losing the main content area. This mirrors VS Code's side panel behavior.

### State

In `App.vue` script setup:
```ts
const reviewOpen = ref(true)  // default: open
```

### When open (`v-if="reviewOpen"`)

A drag handle and the panel itself appear as flex siblings to the center column:

```
[ center column ] [ drag handle 16px ] [ ReviewPanel (width: reviewWidth px) ]
```

- Drag handle: `class="resize-handle shrink-0"`, `@mousedown="startReviewDrag"`
  - Inner structure: `<div class="resize-handle-dashes" />` + `<div class="rust-seam resize-handle-accent" :class="pendingReview ? 'bg-primary-container' : 'bg-outline-variant/30'" />`
- Panel wrapper: `class="shrink-0 overflow-y-auto overflow-x-hidden"`, `:style="{ width: reviewWidth + 'px' }"`
- `reviewWidth` default: 450px, driven by `useResize(450)`

### When closed (`v-else`)

A collapsed tab appears at the right edge:

```
[ center column ] [ 28px collapsed tab ]
```

- Tab: `class="w-7 shrink-0 bg-surface-container flex flex-col items-center justify-center cursor-pointer hover:bg-surface-container-high transition-colors border-l border-outline-variant/20"`
- `@click="reviewOpen = true"`
- Label: `<span style="writing-mode: vertical-rl; transform: rotate(180deg)">⟨⟨ REVIEW</span>`
- Label classes: `text-zinc-600 hover:text-zinc-400 text-[8px] font-mono uppercase tracking-widest select-none`

### Header button

In the header button row:
```html
<button data-testid="btn-review-toggle" @click="reviewOpen = !reviewOpen"
        class="transition-colors p-1"
        :class="reviewOpen ? 'text-secondary' : 'text-zinc-500 hover:text-white'">
  <span class="material-symbols-outlined text-[20px]">dock_to_right</span>
</button>
```

### `useResize` composable

`gui/src/composables/useResize.ts` — supports both axes:

```ts
interface ResizeOptions { min?: number; max?: number; axis?: 'x' | 'y' }

export function useResize(initial: number, options: ResizeOptions = {}) {
  const { min = 300, max = 720, axis = 'x' } = options
  const size = ref(initial)

  function startDrag(e: MouseEvent) {
    e.preventDefault()
    const startCoord = axis === 'x' ? e.clientX : e.clientY
    const startSize = size.value
    function onMove(e: MouseEvent) {
      const current = axis === 'x' ? e.clientX : e.clientY
      size.value = Math.max(min, Math.min(max, startSize + (startCoord - current)))
    }
    function onUp() {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const width = size  // backward-compat alias
  return { size, width, startDrag }
}
```

Usage in App.vue:
```ts
const { width: reviewWidth, startDrag: startReviewDrag } = useResize(450)
```

---

## 2. Terminal Panel

A slide-up panel from the bottom of the main workspace. Width follows the center column (respects whether review panel is open or closed). The terminal is a simple command interpreter — it is NOT a real shell; it talks to the Pinia store.

### State

```ts
const { size: terminalHeight, startDrag: startTerminalDrag } = useResize(260, { min: 120, max: 600, axis: 'y' })
const terminalOpen = ref(false)
```

### Header button

```html
<button data-testid="btn-terminal" @click="terminalOpen = !terminalOpen"
        class="transition-colors p-1"
        :class="terminalOpen ? 'text-secondary' : 'text-zinc-500 hover:text-white'">
  <span class="material-symbols-outlined text-[20px]">terminal</span>
</button>
```

### Placement in App.vue template

The terminal lives inside `<main>`, below the flex row that contains the center column + review panel:

```html
<main class="flex-1 bg-surface-container-low flex flex-col overflow-hidden">
  <div class="flex flex-1 min-h-0 overflow-hidden">
    <!-- center column + review panel -->
  </div>
  <TerminalPanel
    v-if="terminalOpen"
    :height="terminalHeight"
    @close="terminalOpen = false"
    @dragstart="startTerminalDrag"
  />
</main>
```

### `TerminalPanel.vue`

**File:** `gui/src/components/TerminalPanel.vue`

**Props:** `{ height: number }`  
**Emits:** `close`, `dragstart`

**Structure:**
- Outer div: `class="bg-[#0d0f10] border-t border-[#2D2F31] flex flex-col font-mono text-xs"`, `:style="{ height: height + 'px' }"`
- Drag handle bar at top: `class="h-1 cursor-ns-resize shrink-0 bg-[#2D2F31] hover:bg-secondary/40 transition-colors"`, `@mousedown="$emit('dragstart', $event)"`
- Header row: title `SUPERVISOR SHELL`, close button emitting `close`
- Log area: `ref="logEl"`, `class="flex-1 overflow-y-auto p-3 space-y-0.5"`, auto-scrolls on new lines
- Input row at bottom: `<input autocomplete="off" ...>` bound to `inputVal`, `@keydown.enter="submit"`

**Commands (built-in, read from store):**

| Command | Output |
|---------|--------|
| `help` | lists available commands |
| `status` | `STATUS: <store.status> \| THREAD: <store.threadId ?? 'none'>` |
| `workers` | `WORKERS: 4 / 4 ACTIVE` (static placeholder) |
| `clear` | clears the log |

**Line types:** `{ type: 'input' | 'output', text: string }`

**Welcome message** pushed in `onMounted`:
```
OXIDANT SUPERVISOR SHELL v0.1
type "help" for available commands
```

**Auto-scroll:**
```ts
async function pushLine(type: 'input' | 'output', text: string) {
  lines.value.push({ type, text })
  await nextTick()
  if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
}
```

**Visual style:**
- Input line prefix: `>` in `text-secondary`
- Output lines: `text-zinc-400`
- Input echo: `text-zinc-200`
- Header: `text-[10px] uppercase tracking-widest text-zinc-500`

---

## 3. Memory Modal

A smoked-glass modal showing active nodes currently in the Pinia store.

### Composable

**File:** `gui/src/composables/useMemoryModal.ts`

Module-level singleton pattern (shared across all callers):

```ts
import { ref } from 'vue'

const visible = ref(false)
export function useMemoryModal() {
  return {
    visible,
    open:  () => { visible.value = true },
    close: () => { visible.value = false },
  }
}
```

### Header button

```html
<button data-testid="btn-memory" @click="memoryModal.open()"
        class="text-zinc-500 hover:text-white transition-colors p-1">
  <span class="material-symbols-outlined text-[20px]">memory</span>
</button>
```

In App.vue script:
```ts
const memoryModal = useMemoryModal()
```

### `MemoryModal.vue`

**File:** `gui/src/components/MemoryModal.vue`

Uses `<Teleport to="body">` + `<Transition name="modal">`.

**Content:**
- Header: `MEM · ACTIVE NODE CONTEXTS` (text-primary-container, 11px bold uppercase)
- Close button (×) top right
- Dashed divider
- Empty state: `NO ACTIVE NODES` when `Object.keys(store.activeNodes).length === 0`
- Node list: one row per active node showing:
  - Node ID (truncated, `text-zinc-200`)
  - Tier badge: `HAIKU` / `SONNET` / `OPUS` with tier-appropriate color
- Token estimate section (after another dashed divider):
  - Label: `EST. CONTEXT TOKENS`
  - Value: `(nonOpusCount × 8000 + opusCount × 12000).toLocaleString()`

**Modal box style** (same as ConfirmModal pattern):
```css
.modal-box {
  width: 100%;
  max-width: 28rem;
  background: #1e2022;
  border: 1px dashed #57423b;
  border-left: 3px solid #be4d25;
  padding: 24px;
  box-shadow: 0 0 0 1px rgba(190,77,37,0.12), 0 20px 60px rgba(0,0,0,0.8), inset 0 0 40px rgba(190,77,37,0.04);
}
```

Backdrop: `position: fixed; inset: 0; z-index: 999; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.65); backdrop-filter: blur(6px)`

Close on backdrop click (`@mousedown.self="close"`) and Escape (`@keydown.escape.window="close"`).

**Transition:**
```css
.modal-enter-active { transition: opacity 120ms ease-out, transform 120ms ease-out; }
.modal-leave-active { transition: opacity 80ms ease-in, transform 80ms ease-in; }
.modal-enter-from  { opacity: 0; transform: scale(0.96); }
.modal-leave-to    { opacity: 0; transform: scale(0.97); }
```

---

## 4. Sensors Modal

A smoked-glass modal showing live system health metrics. Same visual pattern as MemoryModal.

### Composable

**File:** `gui/src/composables/useSensorsModal.ts`

Same module-level singleton pattern as `useMemoryModal`.

### Header button

```html
<button data-testid="btn-sensors" @click="sensorsModal.open()"
        class="text-zinc-500 hover:text-white transition-colors p-1">
  <span class="material-symbols-outlined text-[20px]">sensors</span>
</button>
```

### `SensorsModal.vue`

**File:** `gui/src/components/SensorsModal.vue`

**Content:**
- Header: `SYS · SYSTEM HEALTH`
- Rows (11px, uppercase, tracking-widest labels):
  - `Supervisor` → status dot + `store.status.toUpperCase()` (dot/text color from status)
  - `Workers` → `4 / 4 ACTIVE` (static)
  - Dashed divider
  - `CPU` → `cpu.toFixed(1)%`
  - `Memory` → `memory.toFixed(1)%`
  - `GPU` → `gpu.toFixed(1)%`

**Live fluctuation:**
```ts
const BASE_CPU    = 34
const BASE_MEMORY = 61
const BASE_GPU    = 78
const FLUCTUATION = 0.05   // ±5%

const cpu    = ref(BASE_CPU)
const memory = ref(BASE_MEMORY)
const gpu    = ref(BASE_GPU)

function fluctuate(base: number): number {
  return base * (1 - FLUCTUATION + Math.random() * FLUCTUATION * 2)
}

const intervalId = setInterval(() => {
  cpu.value    = fluctuate(BASE_CPU)
  memory.value = fluctuate(BASE_MEMORY)
  gpu.value    = fluctuate(BASE_GPU)
}, 2000)

onUnmounted(() => clearInterval(intervalId))
```

**Status dot colors:**
```ts
const statusDotColor = computed(() => {
  switch (store.status) {
    case 'running':     return 'bg-green-400'
    case 'paused':
    case 'interrupted': return 'bg-amber-400'
    case 'error':
    case 'aborted':     return 'bg-red-500'
    default:            return 'bg-zinc-500'
  }
})
```

Same modal box style as MemoryModal.

---

## File Summary

| Action | Path |
|--------|------|
| Create | `gui/src/composables/useResize.ts` |
| Create | `gui/src/composables/useMemoryModal.ts` |
| Create | `gui/src/composables/useSensorsModal.ts` |
| Create | `gui/src/components/TerminalPanel.vue` |
| Create | `gui/src/components/MemoryModal.vue` |
| Create | `gui/src/components/SensorsModal.vue` |
| Modify | `gui/src/App.vue` — wire all of the above |

## Verification

Use `myopex scenarios --config gui/myopex.scenarios.ts --out gui/.myopex-current` after building.  
Compare against `geoff/gui-polish-apr17` branch using `myopex diff`.

Key scenarios to check:
- `memory-modal` — modal opens, node list renders
- `sensors-modal` — modal opens, stats rows visible
- `terminal-open` — panel slides up, welcome message visible, input present
- `review-panel-closed` — collapsed tab visible at right edge, "⟨⟨ REVIEW" label
- `terminal-full-width` — terminal spans full width when review panel is closed

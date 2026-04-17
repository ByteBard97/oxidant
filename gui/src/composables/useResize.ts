import { ref } from 'vue'

interface ResizeOptions {
  min?: number
  max?: number
  axis?: 'x' | 'y'
}

/**
 * Returns a reactive `size` ref and a `startDrag` handler.
 * Attach startDrag to a divider element's @mousedown.
 *
 * axis='x' (default): dragging left widens the right panel; dragging right narrows it.
 * axis='y': dragging up widens the bottom panel; dragging down narrows it.
 *
 * The legacy `width` export is kept as an alias so old call sites keep working
 * until they are migrated to `size`.
 */
export function useResize(initial: number, options: ResizeOptions = {}) {
  const { min = 300, max = 720, axis = 'x' } = options

  const size = ref(initial)

  function startDrag(e: MouseEvent) {
    e.preventDefault()
    const startCoord = axis === 'x' ? e.clientX : e.clientY
    const startSize = size.value

    function onMove(e: MouseEvent) {
      const current = axis === 'x' ? e.clientX : e.clientY
      // dragging toward a smaller coord (left or up) increases the panel size
      size.value = Math.max(min, Math.min(max, startSize + (startCoord - current)))
    }

    function onUp() {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  // Alias so existing `const { width } = useResize(450)` keeps compiling.
  const width = size

  return { size, width, startDrag }
}

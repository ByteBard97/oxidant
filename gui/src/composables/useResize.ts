import { ref } from 'vue'

const MIN_WIDTH = 300   // px — review panel minimum
const MAX_WIDTH = 720   // px — review panel maximum

/**
 * Returns a reactive `width` ref and a `startDrag` handler.
 * Attach startDrag to a divider element's @mousedown.
 * Dragging left widens the right panel; dragging right narrows it.
 */
export function useResize(initialWidth: number) {
  const width = ref(initialWidth)

  function startDrag(e: MouseEvent) {
    e.preventDefault()
    const startX = e.clientX
    const startW = width.value

    function onMove(e: MouseEvent) {
      const delta = startX - e.clientX     // positive = dragged left = wider panel
      width.value = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, startW + delta))
    }

    function onUp() {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  return { width, startDrag }
}

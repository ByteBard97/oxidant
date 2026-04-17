import { ref, onMounted, onUnmounted } from 'vue'

/**
 * Drives a neon-sign flicker with truly random timing.
 * Returns a reactive `opacity` (0–1) to bind as inline style.
 *
 * Three flicker personalities, randomly chosen each event:
 *   stutter  — 1-4 rapid blinks (ms scale), like a loose tube connection
 *   drift    — slow fade down then recovery (power sag)
 *   brownout — stays dim for 1-3 s, then snaps back
 */
export function useNeonFlicker() {
  const opacity = ref(1)
  let nextId: ReturnType<typeof setTimeout> | null = null
  const timers: ReturnType<typeof setTimeout>[] = []

  function rng(min: number, max: number) {
    return min + Math.random() * (max - min)
  }

  function after(ms: number, fn: () => void) {
    const id = setTimeout(fn, ms)
    timers.push(id)
    return id
  }

  function stutter() {
    const drops = 1 + Math.floor(rng(0, 4))   // 1–4 blinks
    let cursor = 0
    for (let i = 0; i < drops; i++) {
      const dimOpacity  = rng(0.15, 0.65)
      const dimDuration = rng(20, 90)
      const gapBefore   = cursor + rng(0, 60)
      after(gapBefore, () => { opacity.value = dimOpacity })
      after(gapBefore + dimDuration, () => {
        // snap back to slightly-below-one before full recovery
        opacity.value = rng(0.85, 0.97)
      })
      after(gapBefore + dimDuration + rng(20, 80), () => {
        opacity.value = 1.0
      })
      cursor = gapBefore + dimDuration + 120
    }
  }

  function drift() {
    const target   = rng(0.45, 0.75)
    const downTime = rng(80, 250)
    const holdTime = rng(100, 400)
    const upTime   = rng(60, 180)
    opacity.value = target
    after(downTime, () => {
      opacity.value = rng(target - 0.1, target + 0.05)
    })
    after(downTime + holdTime, () => {
      opacity.value = rng(0.88, 0.97)
    })
    after(downTime + holdTime + upTime, () => {
      opacity.value = 1.0
    })
  }

  function brownout() {
    const dimLevel = rng(0.50, 0.72)
    const holdMs   = rng(800, 3200)
    opacity.value  = dimLevel
    after(holdMs, () => {
      // sometimes: stutter back
      if (Math.random() < 0.4) stutter()
      else opacity.value = 1.0
    })
  }

  function scheduleNext() {
    // Quiet window between events: 400 ms – 9 s
    // Weighted toward long pauses (sign mostly stable)
    const quietMs = Math.random() < 0.7
      ? rng(2000, 9000)   // long calm
      : rng(400, 1800)    // short calm (cluster of activity)

    nextId = setTimeout(() => {
      const roll = Math.random()
      if      (roll < 0.50) stutter()
      else if (roll < 0.80) drift()
      else                   brownout()

      scheduleNext()
    }, quietMs)
  }

  onMounted(() => scheduleNext())

  onUnmounted(() => {
    if (nextId) clearTimeout(nextId)
    timers.forEach(clearTimeout)
  })

  return { opacity }
}

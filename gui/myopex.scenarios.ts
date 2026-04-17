// myopex.scenarios.ts — Oxidant GUI
// Run: myopex scenarios --config myopex.scenarios.ts --out .myopex-baseline
import type { Scenario } from 'myopex'

// Click the seed-data button via its testid
const seedSteps = [
  { click: '[data-testid=btn-seed]' },
  { wait: 400 },
]

const scenarios: Scenario[] = [

  // ── 1. Default empty state (logs tab, no data) ────────────────────────────
  { name: 'default-empty' },

  // ── 2. Run controls tab ───────────────────────────────────────────────────
  {
    name: 'tab-run-controls',
    steps: [
      { click: '[data-testid=nav-run]' },
      { wait: 150 },
    ],
  },

  // ── 3. Review queue tab — empty ───────────────────────────────────────────
  {
    name: 'tab-review-queue-empty',
    steps: [
      { click: '[data-testid=nav-review]' },
      { wait: 150 },
    ],
  },

  // ── 4. Logs tab with seeded pipeline data ─────────────────────────────────
  {
    name: 'logs-with-data',
    steps: [
      ...seedSteps,
      { click: '[data-testid=nav-logs]' },
      { wait: 200 },
    ],
  },

  // ── 5. Review queue with data (errors + interrupts) ───────────────────────
  {
    name: 'review-queue-with-data',
    steps: [
      ...seedSteps,
      { click: '[data-testid=nav-review]' },
      { wait: 200 },
    ],
  },

  // ── 6. Memory modal open (with active nodes from seed) ────────────────────
  {
    name: 'memory-modal',
    steps: [
      ...seedSteps,
      { click: '[data-testid=btn-memory]' },
      { wait: 200 },
    ],
  },

  // ── 7. Sensors modal open ─────────────────────────────────────────────────
  {
    name: 'sensors-modal',
    steps: [
      { click: '[data-testid=btn-sensors]' },
      { wait: 200 },
    ],
  },

  // ── 8. Terminal panel open ────────────────────────────────────────────────
  {
    name: 'terminal-open',
    steps: [
      { click: '[data-testid=btn-terminal]' },
      { wait: 200 },
    ],
  },

  // ── 9. Terminal with status command output ────────────────────────────────
  {
    name: 'terminal-with-command',
    steps: [
      ...seedSteps,
      { click: '[data-testid=btn-terminal]' },
      { wait: 200 },
      { press: 'input[autocomplete=off]', key: 'End' },
    ],
    setup: async (page) => {
      const input = page.locator('input[autocomplete=off]')
      await input.fill('status')
      await input.press('Enter')
      await page.waitForTimeout(200)
    },
  },

  // ── 10. Review panel closed — collapsed tab visible ───────────────────────
  {
    name: 'review-panel-closed',
    steps: [
      { click: '[data-testid=btn-review-toggle]' },
      { wait: 200 },
    ],
  },

  // ── 11. Terminal open + review panel closed (terminal fills full width) ────
  {
    name: 'terminal-full-width',
    steps: [
      { click: '[data-testid=btn-review-toggle]' },
      { wait: 150 },
      { click: '[data-testid=btn-terminal]' },
      { wait: 200 },
    ],
  },

]

export default scenarios

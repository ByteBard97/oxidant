// myopex.scenarios.ts — oxidant GUI audit
// Run: /Users/ceres/Desktop/SignalCanvas/ui-audit/bin/myopex.sh scenarios \
//        --url http://localhost:8000 \
//        --config myopex.scenarios.ts \
//        --out .myopex-oxidant

import type { Scenario } from '/Users/ceres/Desktop/SignalCanvas/ui-audit/src/scenarios'

// Helper: inject Pinia store state via the window.__pinia registry
const injectStore = (patch: string) =>
  `(function() {
    const store = window.__pinia?.state?.value?.run;
    if (!store) { console.warn('Pinia run store not found'); return; }
    Object.assign(store, ${patch});
  })()`

const scenarios: Scenario[] = [
  // ── 1. Idle (fresh load) ─────────────────────────────────────────────────
  {
    name: 'idle',
    // Default state: no run started, all buttons resting
  },

  // ── 2. Running — nodes in flight, some stats ─────────────────────────────
  {
    name: 'running',
    setup: async (page) => {
      await page.evaluate(`
        (function() {
          const store = window.__pinia?.state?.value?.run;
          if (!store) return;
          store.status = 'running';
          store.threadId = 'thread-abc123';
          store.stats = { converted: 42, needsReview: 3, inProgress: 2 };
          store.activeNodes = {
            'src/layout/GeomGraph.ts/GeomGraph': {
              node_id: 'src/layout/GeomGraph.ts/GeomGraph',
              tier: 'haiku',
              status: 'translating',
              attempts: 1,
              startedAt: Date.now(),
            },
            'src/routing/SplineRouter.ts/SplineRouter': {
              node_id: 'src/routing/SplineRouter.ts/SplineRouter',
              tier: 'sonnet',
              status: 'translating',
              attempts: 2,
              startedAt: Date.now(),
            },
          };
          store.recentEvents = [
            JSON.stringify({ event: 'node_start', node_id: 'src/routing/SplineRouter.ts/SplineRouter', tier: 'sonnet' }),
            JSON.stringify({ event: 'node_complete', node_id: 'src/layout/GeomNode.ts/GeomNode', tier: 'haiku', attempts: 1 }),
            JSON.stringify({ event: 'node_escalate', node_id: 'src/layout/GeomGraph.ts/GeomGraph', from_tier: 'haiku', to_tier: 'sonnet' }),
            JSON.stringify({ event: 'node_start', node_id: 'src/layout/GeomGraph.ts/GeomGraph', tier: 'haiku' }),
          ];
        })()
      `)
    },
  },

  // ── 3. Paused ─────────────────────────────────────────────────────────────
  {
    name: 'paused',
    setup: async (page) => {
      await page.evaluate(`
        (function() {
          const store = window.__pinia?.state?.value?.run;
          if (!store) return;
          store.status = 'paused';
          store.threadId = 'thread-abc123';
          store.stats = { converted: 42, needsReview: 3, inProgress: 0 };
          store.activeNodes = {};
          store.recentEvents = [
            JSON.stringify({ event: 'node_complete', node_id: 'src/layout/GeomNode.ts/GeomNode', tier: 'haiku', attempts: 1 }),
          ];
        })()
      `)
    },
  },

  // ── 4. Interrupted — ReviewPanel overlay ─────────────────────────────────
  {
    name: 'interrupted',
    setup: async (page) => {
      await page.evaluate(`
        (function() {
          const store = window.__pinia?.state?.value?.run;
          if (!store) return;
          store.status = 'interrupted';
          store.threadId = 'thread-abc123';
          store.stats = { converted: 42, needsReview: 3, inProgress: 0 };
          store.activeNodes = {};
          store.pendingReview = {
            node_id: 'src/routing/SplineRouter.ts/SplineRouter.computeRoutes',
            error: 'Cannot infer return type: complex async iterator with multiple yield types',
            supervisor_hint: 'Break the async iterator into a separate function. The yield type is Edge[].',
            source_preview: 'async *computeRoutes(edges: Edge[]): AsyncGenerator<Edge[], void> {\n  for (const batch of chunk(edges, 20)) {\n    yield await this.routeBatch(batch);\n  }\n}',
          };
        })()
      `)
    },
  },

  // ── 5. Complete ───────────────────────────────────────────────────────────
  {
    name: 'complete',
    setup: async (page) => {
      await page.evaluate(`
        (function() {
          const store = window.__pinia?.state?.value?.run;
          if (!store) return;
          store.status = 'complete';
          store.threadId = 'thread-abc123';
          store.stats = { converted: 218, needsReview: 12, inProgress: 0 };
          store.activeNodes = {};
          store.recentEvents = [
            JSON.stringify({ event: 'run_complete', converted: 218, needs_review: 12 }),
            JSON.stringify({ event: 'node_complete', node_id: 'src/layout/GeomGraph.ts/GeomGraph', tier: 'opus', attempts: 3 }),
          ];
        })()
      `)
    },
  },

  // ── 6. Aborted ────────────────────────────────────────────────────────────
  {
    name: 'aborted',
    setup: async (page) => {
      await page.evaluate(`
        (function() {
          const store = window.__pinia?.state?.value?.run;
          if (!store) return;
          store.status = 'aborted';
          store.threadId = 'thread-abc123';
          store.stats = { converted: 11, needsReview: 1, inProgress: 0 };
          store.activeNodes = {};
        })()
      `)
    },
  },
]

export default scenarios

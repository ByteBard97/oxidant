/**
 * Development-only mock data seeder.
 * Pumps realistic events through the store's applyEvent() pipeline so the
 * full UI can be visually tested without a running backend.
 */
import { useRunStore } from '../store'

const NODE_IDS = [
  'src/layout/GraphClusterer.ts',
  'src/routing/EdgeRouter.ts',
  'src/layout/LayeredLayout.ts',
  'src/geometry/Rectangle.ts',
  'src/geometry/Point.ts',
  'src/core/Graph.ts',
  'src/core/Node.ts',
  'src/core/Edge.ts',
  'src/sugiyama/SugiyamaLayout.ts',
  'src/sugiyama/crossing/BarycentricHeuristic.ts',
  'src/sugiyama/ordering/LayerByLayerSweep.ts',
  'src/math/Vector2D.ts',
  'src/math/Matrix.ts',
  'src/rendering/CanvasRenderer.ts',
  'src/rendering/SVGRenderer.ts',
  'src/io/DotParser.ts',
  'src/io/JsonExporter.ts',
  'src/utils/PriorityQueue.ts',
  'src/utils/UnionFind.ts',
  'src/algorithms/Dijkstra.ts',
]

const TIERS = ['haiku', 'sonnet', 'opus']
const ERRORS = [
  `Type 'HashMap<String, Box<dyn Any>>' cannot be used as a trait object bound\n  → generic parameter T is not constrained by the impl`,
  `Lifetime 'a does not outlive 'b in return position\n  → consider adding explicit lifetime annotations`,
  `Cannot move out of 'node_map' because it is borrowed\n  → consider using Arc<Mutex<...>> for shared ownership`,
]

function e(obj: object): string {
  return JSON.stringify(obj)
}

function pick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]
}

export function seedMockData() {
  const store = useRunStore()
  store.reset()
  store.setThreadId('mock-thread-dev-001')

  // ── Historical events (appear in telemetry feed, newest first) ──────────────
  const history: string[] = []

  // Run opened
  history.push(e({ event: 'status', status: 'running', message: 'Run initialised — 20 nodes queued' }))

  // Simulate 14 completed conversions + some escalations
  const completedIds = NODE_IDS.slice(0, 14)
  completedIds.forEach((id, i) => {
    const tier = TIERS[i % 3]
    history.push(e({ event: 'node_start',    node_id: id, tier }))
    if (i % 4 === 2) {
      const nextTier = TIERS[Math.min(TIERS.indexOf(tier) + 1, 2)]
      history.push(e({ event: 'node_escalate', node_id: id, from_tier: tier, to_tier: nextTier }))
      history.push(e({ event: 'supervisor',    node_id: id, hint: 'Use Box<dyn Trait> for heterogeneous collections', requires_human: false }))
    }
    history.push(e({ event: 'node_complete', node_id: id, tier, attempts: 1 + (i % 3) }))
  })

  // 3 nodes that failed → needs_review
  const failedIds = NODE_IDS.slice(14, 17)
  failedIds.forEach(id => {
    history.push(e({ event: 'node_start', node_id: id, tier: 'opus' }))
    history.push(e({ event: 'error',      node_id: id, message: pick(ERRORS) }))
  })

  // Apply oldest-first so store builds correct state
  ;[...history].reverse().forEach(raw => store.applyEvent(raw))

  // ── 3 nodes actively processing right now ───────────────────────────────────
  const activeIds = NODE_IDS.slice(17, 20)
  activeIds.forEach((id, i) => {
    store.applyEvent(e({ event: 'node_start', node_id: id, tier: TIERS[i] }))
  })

  // ── Pending human review (activates the Review Panel) ───────────────────────
  store.applyEvent(e({
    event: 'interrupt',
    node_id: 'src/sugiyama/crossing/BarycentricHeuristic.ts',
    payload: {
      node_id:         'src/sugiyama/crossing/BarycentricHeuristic.ts',
      error:           ERRORS[0],
      supervisor_hint: 'Try HashMap<String, Box<dyn Crossings>> with a custom trait',
      source_preview:  `export class BarycentricHeuristic implements ICrossingReduction {\n  private readonly nodeMap: Map<string, any> = new Map()\n\n  reduce(layers: ILayerArrays, dag: GeomGraph): void {\n    layers.forEach((layer, i) => {\n      layer.forEach(node => this.nodeMap.set(node.id, { layer: i, node }))\n    })\n  }\n}`,
    },
  }))
}

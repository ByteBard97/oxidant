# Data Store

All conversion state lives in a single SQLite file: `oxidant.db`. It is the source of truth for all phases.

---

## Tables

### `nodes`

One row per manifest node.

| Column | Type | Description |
|--------|------|-------------|
| `node_id` | TEXT PK | e.g. `SweepEvent__addEvent` |
| `source_file` | TEXT | Relative TypeScript path, e.g. `modules/layout/src/sweep_event.ts` |
| `line_start` / `line_end` | INT | Line range in the source file |
| `source_text` | TEXT | Full TypeScript source of this node |
| `node_kind` | TEXT | `class \| method \| constructor \| getter \| setter \| free_function \| interface \| enum \| type_alias` |
| `parameter_types` | JSON | `{"paramName": "TypeScript type string"}` |
| `return_type` | TEXT | TypeScript return type string |
| `type_dependencies` | JSON | Node IDs this node references by type |
| `call_dependencies` | JSON | Node IDs this node calls at runtime |
| `callers` | JSON | Node IDs that call this node |
| `parent_class` | TEXT | Class name if this is a method/constructor |
| `cyclomatic_complexity` | INT | Number of independent paths through the code |
| `idioms_needed` | JSON | Idiom tags detected by `detect_idioms.ts` |
| `topological_order` | INT | Position in dependency-sorted order |
| `bfs_level` | INT | BFS level (for parallelism grouping) |
| `tier` | TEXT | `haiku \| sonnet \| opus` |
| `status` | TEXT | `not_started \| in_progress \| converted \| failed \| human_review` |
| `snippet_path` | TEXT | Path to the saved `.rs` snippet once converted |
| `attempt_count` | INT | Number of conversion attempts made |
| `last_error` | TEXT | Error from most recent failed attempt |

### `manifest_meta`

Single-row metadata: source repo path, schema version, generation timestamp.

---

## Concurrency

The DB uses **WAL mode** (`PRAGMA journal_mode=WAL`), which allows concurrent readers alongside a single writer. This is what makes parallel workers safe.

The `claim_next_eligible()` method performs an atomic `SELECT + UPDATE` in a single transaction, so no two workers ever claim the same node.

---

## Accessing the manifest

All code goes through the `Manifest` class in `models/manifest.py`:

```python
from oxidant.models.manifest import Manifest
from pathlib import Path

m = Manifest.load(Path("oxidant.db"))

# Read a node
node = m.nodes["SweepEvent__addEvent"]

# Update node status (single-row write, not a full file rewrite)
m.update_node(Path("oxidant.db"), node.node_id, status=NodeStatus.CONVERTED)

# Claim the next eligible node atomically
node = m.claim_next_eligible()
```

The `nodes` property performs a `SELECT *` — use sparingly in hot loops. `claim_next_eligible()` uses a targeted SQL query.

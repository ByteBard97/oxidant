# Oxidant — Architecture Reference

**Status:** Current as of April 2026  
**What this document is:** A ground-truth description of what is actually built and running, not aspirational. See `OXIDANT_PRD.md` for the full vision.

---

## What Oxidant Is

Oxidant is a Python harness that converts TypeScript codebases to Rust by orchestrating Claude Code subprocesses. It does not translate code itself — it decides *what* to translate, *in what order*, with *what context*, and whether the output is *acceptable*.

The primary corpus is **msagl-js** — Microsoft's TypeScript graph layout engine (~4,800 functions).

---

## High-Level Flow

```
TypeScript repo
    │
    ▼
[Phase A] ts-morph AST extractor (TypeScript script)
    │  Produces: oxidant.db (SQLite)
    ▼
[Phase A] Skeleton generator (generate_skeleton.py)
    │  Produces: corpora/msagl-rs/ — a compilable Rust project
    │  Every function body = todo!("OXIDANT: not yet translated — <node_id>")
    ▼
[Phase B] LangGraph translation loop
    │  For each node in topological order:
    │    1. Build prompt (TypeScript source + Rust skeleton + dependency snippets)
    │    2. Invoke Claude Code subprocess
    │    3. Verify: stub check → branch parity → cargo check
    │    4. On pass: save snippet, mark converted in DB
    │    5. On fail: retry with error context; escalate tier after N failures
    ▼
Rust project with all todo!() stubs replaced by real implementations
```

---

## Data Store: `oxidant.db`

A single SQLite file is the source of truth for all conversion state. Two tables:

**`nodes`** — one row per manifest node (class, method, function, etc.)

| Column | Type | Description |
|--------|------|-------------|
| `node_id` | TEXT PK | e.g. `sweep_event__SweepEvent__addEvent` |
| `source_file` | TEXT | relative path in the TypeScript repo |
| `line_start` / `line_end` | INT | line range in the source file |
| `source_text` | TEXT | full TypeScript source of this node |
| `node_kind` | TEXT | `class`, `method`, `constructor`, `interface`, `enum`, `free_function`, etc. |
| `parameter_types` | JSON | `{paramName: "TypeScript type"}` |
| `return_type` | TEXT | TypeScript return type |
| `type_dependencies` | JSON | list of node_ids this node depends on by type |
| `call_dependencies` | JSON | list of node_ids this node calls |
| `callers` | JSON | list of node_ids that call this node |
| `parent_class` | TEXT | class name if this is a method/constructor |
| `cyclomatic_complexity` | INT | branch count |
| `idioms_needed` | JSON | idiom tags detected by the idiom scanner |
| `topological_order` | INT | position in dependency-sorted order |
| `bfs_level` | INT | BFS level for parallelism grouping |
| `tier` | TEXT | `haiku` / `sonnet` / `opus` |
| `status` | TEXT | `not_started` / `in_progress` / `converted` / `failed` / `human_review` |
| `snippet_path` | TEXT | path to the saved Rust snippet file on disk |
| `attempt_count` | INT | number of conversion attempts |
| `last_error` | TEXT | error from most recent failed attempt |

**`manifest_meta`** — single-row metadata (source repo path, schema version, generation timestamp)

The DB is accessed concurrently by parallel workers using SQLite WAL mode. The `claim_next_eligible()` method does an atomic SELECT + UPDATE in a single transaction so no two workers claim the same node.

---

## Phase A: Analysis and Skeleton Generation

### A1 — AST Extraction (`phase_a_scripts/extract_ast.ts`)

A ts-morph TypeScript script that parses the entire source codebase and populates `oxidant.db`. For each translatable unit it records: node ID, source location, full source text, TypeScript types, dependency edges, call graph edges, cyclomatic complexity, BFS level, and topological order.

**Node kinds extracted:**
- `class` — the class definition (fields only, no method bodies)
- `constructor` — constructor body
- `method`, `getter`, `setter` — individual method bodies  
- `free_function` — module-level functions
- `interface` — TypeScript interface (becomes a Rust trait)
- `enum` — TypeScript enum (becomes a Rust enum)
- `type_alias` — TypeScript type aliases

### A2 — Tier Classification (`analysis/classify_tiers.py`)

A Haiku pass over every node in the DB assigns a translation tier based on cyclomatic complexity and idioms detected. Tiers determine which Claude model handles conversion and how many retries are permitted before escalation.

### A3 — Skeleton Generation (`analysis/generate_skeleton.py` + `analysis/hierarchy.py`)

A deterministic Python script that reads `oxidant.db` and writes a complete, compilable Rust project to `corpora/msagl-rs/`. This is the most mechanically complex part of Phase A.

**What the skeleton contains:**
- `Cargo.toml` with the approved crate inventory
- `src/lib.rs` with `pub mod` declarations for every module
- One `.rs` file per TypeScript source file
- `pub struct` / `pub enum` / `pub trait` / `pub fn` declarations for every node
- `todo!("OXIDANT: not yet translated — <node_id>")` as the body for every function

**Type mapping** (`map_ts_type`): TypeScript types are converted to Rust equivalents. Cross-module references use fully-qualified `crate::module::Type` paths so no `use` imports are needed. Key mappings:

| TypeScript | Rust |
|-----------|------|
| `number` | `f64` |
| `string` | `String` |
| `boolean` | `bool` |
| `T[]` / `Array<T>` | `Vec<T>` |
| `Map<K,V>` | `std::collections::HashMap<K,V>` |
| `Set<T>` | `std::collections::HashSet<T>` |
| `T \| null` | `Option<T>` |
| DOM/Web types | `serde_json::Value` |
| User class `Foo` (same module) | `Rc<RefCell<Foo>>` |
| User class `Foo` (other module) | `Rc<RefCell<crate::module::Foo>>` |
| TypeScript interface `IFoo` | `Rc<dyn IFoo>` |

---

## Class Hierarchy Handling

msagl-js has 101 classes using `extends`, forming 22 distinct parent-child hierarchies. The skeleton generator classifies each hierarchy as one of two kinds and emits different Rust representations accordingly. This classification is hardcoded in `KNOWN_HIERARCHIES` (`analysis/hierarchy.py`), validated against a manual Rust port of msagl-js (`Routers/msagl-rust`).

### Category A — Discriminated Unions → `pub enum`

These are hierarchies where each subclass adds 0–3 unique fields and the TypeScript code dispatches on type using `instanceof`. In Rust, these *must* be enums — there is no runtime discriminant available on a flat struct.

**Classified as enum:** `SweepEvent`, `VertexEvent`, `BasicVertexEvent`, `BasicReflectionEvent`, `Layer`, `OptimalPacking`

**What the skeleton emits** (in the base class's `.rs` file):

```rust
#[derive(Debug, Clone)]
pub enum SweepEvent {
    AxisCoordinateEvent { site: Rc<RefCell<crate::point::Point>> },
    AxisEdgeHighPointEvent { site: Rc<RefCell<crate::point::Point>>, axis_edge: Rc<RefCell<crate::axis_edge::AxisEdge>> },
    BasicReflectionEvent(crate::basic_reflection_event::BasicReflectionEvent),
    ConeClosureEvent { cone_to_close: Rc<RefCell<crate::cone::Cone>>, site: Rc<RefCell<crate::point::Point>> },
    VertexEvent(crate::vertex_event::VertexEvent),
    // ...
}
```

Each child class's fields become named fields of the variant. Sub-hierarchies that are themselves enum bases (e.g. `VertexEvent` is a child of `SweepEvent` but also a hierarchy base) are represented as tuple variants wrapping the child enum type, which is emitted in its own module.

**Child class `.rs` files:** Child classes that have been folded into a parent enum are *skipped* in the struct emission loop — they get no `pub struct` of their own.

**Type redirect table** (`_enum_child_redirect`): When method signatures in other modules reference a now-folded child type (e.g. `PortObstacleEvent`), the type mapper redirects those references to the parent enum type (`crate::sweep_event::SweepEvent`) so they still compile.

### Category B — Behavior Hierarchies → Struct Composition

These are hierarchies where each subclass is a large independent class that happens to share a base. Struct composition is idiomatic Rust for this pattern.

**Classified as struct:** `Algorithm`, `Attribute`, `SegmentBase`, `LineSweeperBase`, `GeomObject`, `BasicGraphOnEdges`, `Entity`, `Port`, `DrawingObject`, `SvgViewerObject`, `ObstacleSide`, `BasicObstacleSide`, `ConeSide`, `VisibilityEdge`, `KdNode`, `Packing`

**What the skeleton emits** (in each child class's `.rs` file):

```rust
#[derive(Debug, Clone)]
pub struct SplineRouter {
    pub base: crate::algorithm::Algorithm,  // ← first field, cross-module reference
    pub continue_on_overlaps: bool,
    pub obstacle_calculator: Rc<RefCell<crate::shape_obstacle_calculator::ShapeObstacleCalculator>>,
    // ... child's own fields
}
```

When agents convert methods that call `super.method()`, they write `self.base.method()`.

### External parents

If a class extends a TypeScript type that is not in the manifest corpus (e.g. browser built-ins like `EventSource`), the skeleton emits a comment instead:

```rust
pub struct MyClass {
    // NOTE: extends EventSource (external — not in corpus)
    // ...fields
}
```

---

## Phase B: Translation Loop

The translation loop is a LangGraph state graph defined in `graph/graph.py`. It runs as a Python process and drives one or more Claude Code subprocesses.

### State (`graph/state.py`)

`OxidantState` is a TypedDict that LangGraph passes between nodes:

```python
class OxidantState(TypedDict):
    db_path: str           # absolute path to oxidant.db
    target_path: str       # absolute path to the skeleton Rust project
    snippets_dir: str      # where completed snippet .rs files are saved
    config: dict           # parsed oxidant.config.json
    worker_id: int         # which worker clone this process uses (for parallelism)

    current_node_id: str   # the node being processed right now
    current_prompt: str    # the prompt sent to Claude
    current_snippet: str   # the Rust body text Claude returned
    current_tier: str      # "haiku" | "sonnet" | "opus"
    attempt_count: int     # retry counter for the current node
    last_error: str        # error from the most recent failed attempt
    verify_status: str     # "PASS" | "STUB" | "BRANCH" | "CARGO"

    review_queue: list     # nodes queued for human review (append-only)
    done: bool             # True when no more eligible nodes remain
    max_nodes: int         # optional cap on nodes processed per run
    nodes_this_run: int    # counter for the cap

    supervisor_hint: str   # hint injected after a supervisor review
    review_mode: str       # "auto" | "interactive" | "supervised"
```

### Graph Nodes

```
pick_next_node
    │  Atomically claims the next eligible node from SQLite.
    │  Eligible = NOT_STARTED + all dependencies are CONVERTED.
    │  In single-worker mode, also resets orphaned IN_PROGRESS nodes.
    ↓ (done → END)
build_context
    │  Assembles the full conversion prompt:
    │    - TypeScript source file path + line range
    │    - Rust skeleton file path
    │    - Already-converted Rust snippets for all dependencies
    │    - Idiom dictionary entries for this node's detected patterns
    │    - Retry context (previous error) if attempt_count > 0
    │    - Supervisor hint if provided
    ↓
invoke_agent
    │  Invokes `claude --print` as a subprocess.
    │  ANTHROPIC_API_KEY is stripped from the environment to force
    │  Max subscription auth (not pay-per-token API billing).
    │  Saves the returned Rust body text to state.current_snippet.
    ↓
verify
    │  Three checks in cost order (cheapest first):
    │    1. Stub check: grep for todo!() / unimplemented!()
    │    2. Branch parity: Rust branch count ≥ 60% of TypeScript branch count
    │    3. cargo check: inject snippet into skeleton, run cargo check, restore
    │  Sets state.verify_status.
    ↓ (conditional)
    ├─ PASS → update_manifest → pick_next_node
    ├─ STUB/BRANCH (under attempt limit) → retry_node → build_context
    ├─ CARGO (under attempt limit) → retry_node → build_context (with error)
    ├─ (over haiku limit) → escalate_node → build_context (higher tier)
    ├─ (over escalated limit) → supervisor_node → build_context or queue_for_review
    └─ (exhausted all tiers) → queue_for_review → pick_next_node
```

### Prompt Structure (`agents/context.py`)

Each prompt contains:

1. **Task description** — which node to implement, what files to read
2. **File paths** — absolute paths to the TypeScript source file and the Rust skeleton `.rs` file
3. **Rules** — no `todo!()`, pure ASCII output, faithful translation, no simplification, only approved crates
4. **Architectural Decisions** — from `oxidant.config.json` (e.g. graph ownership strategy)
5. **Converted Dependencies** *(optional)* — Rust snippet bodies for functions this node calls, loaded from `snippets/` by following `snippet_path` in the DB for each `call_dependencies` + `type_dependencies` entry
6. **Idiom Translations** *(optional)* — relevant sections from `idiom_dictionary.md` for the idiom tags on this node
7. **Previous Attempt Failed** *(optional, on retry)* — the cargo check or verification error from the last attempt
8. **Supervisor Hint** *(optional)* — hint injected after a human or supervisor review

The agent is instructed to:
- Read the TypeScript source file itself
- Read the Rust skeleton file to understand available types and signatures
- Implement only the one function body identified by `todo!("OXIDANT: not yet translated — <node_id>")`
- Run `cargo check` in the skeleton directory and fix any errors
- Output the final function body text (no markdown fences) when done

### Verification (`verification/verify.py`)

**Step 1 — Stub check**: Searches for `todo!()` or `unimplemented!()` in the snippet. Instant fail.

**Step 2 — Branch parity**: Counts branch constructs (`if`/`else`/`switch`/`case`/`for`/`while`/`?`) in the TypeScript source and `if`/`else`/`match`/`for`/`while`/`loop` in the Rust output. If the TypeScript has ≥3 branches and the Rust has fewer than 60%, fails with a diagnostic.

**Step 3 — cargo check**: 
1. Locates the `todo!("OXIDANT: not yet translated — <node_id>")` marker in the skeleton `.rs` file
2. Replaces it with the snippet
3. Runs `cargo check --message-format=short`
4. Always restores the original file (in a `finally` block)
5. If compilation fails, distinguishes between failures in the target file (the snippet is bad → `CARGO`) vs failures in other files (a previously-converted snippet is broken → `CASCADE`, retry later)

### Parallelism

Multiple worker processes can run simultaneously. Each worker uses its own clone of the skeleton project at `target_path/.clone_N/` so concurrent cargo check invocations don't race on the same files. The atomic `claim_next_eligible()` SQL transaction prevents duplicate work.

---

## Serving / GUI (`serve/`)

`oxidant serve` starts a FastAPI server that exposes the translation loop over HTTP. This allows a Vue 3 GUI to control and monitor Phase B runs without being in a terminal.

**Endpoints:**
- `POST /run` — start or resume a Phase B run
- `GET /stream/{thread_id}` — SSE stream of progress events
- `POST /pause/{thread_id}` — pause after current node
- `POST /resume/{thread_id}` — resume after a supervisor interrupt
- `GET /review-queue` — nodes awaiting human review
- `GET /status/{thread_id}` — run status snapshot

The serve mode uses `SqliteSaver` as the LangGraph checkpointer, enabling durable resume of interrupted runs.

---

## Repository Layout

```
oxidant/
  oxidant.config.json           ← project config (source/target repos, crate inventory)
  oxidant.db                    ← SQLite: all node state (created by extract_ast.ts)

  src/oxidant/
    analysis/
      generate_skeleton.py      ← writes the Rust skeleton project
      hierarchy.py              ← classifies class hierarchies (enum vs struct)
      classify_tiers.py         ← assigns haiku/sonnet/opus tier to each node
    agents/
      context.py                ← builds the conversion prompt for one node
      invoke.py                 ← invokes `claude --print` as a subprocess
    graph/
      graph.py                  ← LangGraph graph wiring
      nodes.py                  ← LangGraph node functions
      state.py                  ← OxidantState TypedDict
    models/
      manifest.py               ← Manifest class: SQLite-backed, Pydantic node model
      db.py                     ← SQLModel table definitions
    verification/
      verify.py                 ← stub / branch-parity / cargo-check pipeline
    assembly/
      assemble.py               ← assembles completed snippets into final .rs files
    serve/
      app.py                    ← FastAPI app (oxidant serve)
      run_manager.py            ← manages async Phase B runs for the server
      events.py                 ← SSE event streaming
    refinement/
      clippy_runner.py          ← Phase C: runs cargo clippy
      categorize.py             ← categorizes clippy warnings by fix type
      phase_c.py                ← Phase C orchestration
    cli.py                      ← Typer CLI entry point

  phase_a_scripts/
    extract_ast.ts              ← ts-morph extractor → oxidant.db
    detect_idioms.ts            ← idiom pattern scanner

  corpora/
    msagljs/                    ← TypeScript source (gitignored)
    msagl-rs/                   ← generated Rust skeleton (gitignored)
      src/
        lib.rs
        sweep_event.rs          ← pub enum SweepEvent { ... }
        algorithm.rs            ← pub struct Algorithm { ... }
        spline_router.rs        ← pub struct SplineRouter { pub base: crate::algorithm::Algorithm, ... }
        ...

  snippets/                     ← saved Rust snippet bodies (one .rs per node)
  idiom_dictionary.md           ← human-reviewed TS→Rust idiom map
  docs/
    OXIDANT_PRD.md              ← full product requirements document
    ARCHITECTURE.md             ← this file
    RESEARCH_SUMMARY.md
    RESEARCH_ACADEMIC.md
```

---

## Key Design Decisions

### Skeleton-first
The skeleton generator runs before any AI involvement. By the time Claude touches a file, `cargo check` already passes on the whole project. This means every agent invocation gets meaningful compiler feedback, not empty-project errors.

### Topological order
Nodes are converted in dependency order. When agent converts function A, every function A calls has already been converted and its snippet is available. The prompt includes those snippet bodies under `## Converted Dependencies`.

### Per-node granularity
Each function body is converted and verified independently. A failure in one node doesn't block others. Progress is resumable — the DB records which nodes are done. Parallelism is safe because each worker has its own skeleton clone.

### Subprocess invocation
Claude Code is invoked as `claude --print` with `ANTHROPIC_API_KEY` stripped, forcing Max subscription auth. The Python SDK requires API key auth (pay-per-token), which is prohibitively expensive for a 4,800-node run.

### Hierarchy-aware skeleton
The skeleton generator does not emit flat structs for every class. It classifies class hierarchies and emits the correct Rust representation (enum variants for discriminated unions, `pub base:` field for behavior hierarchies). This is essential because agents have no memory between invocations — if the scaffold is wrong, every agent in that hierarchy family independently invents a broken representation.

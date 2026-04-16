# Phase A — Analysis Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase A pipeline that converts the msagljs TypeScript codebase into a `conversion_manifest.json` (all nodes annotated with dependencies, idiom patterns, and translation tiers) and a compilable Rust skeleton project at `corpora/msagl-rs/`.

**Architecture:** Four sequential scripts invoked by `oxidant phase-a`: (1) `tsx extract_ast.ts` walks the ts-morph AST and writes the initial manifest; (2) `tsx detect_idioms.ts` annotates each node with idiom patterns; (3) `classify_tiers.py` calls Claude Haiku to assign translation tiers; (4) `generate_skeleton.py` produces a compilable Rust project with `todo!("OXIDANT: …")` stubs in every function body. The `conversion_manifest.json` is the shared data artifact written after each step.

**Tech Stack:** Python 3.11, Pydantic v2, Anthropic Python SDK (Haiku tier calls); tsx + ts-morph (Phase A TypeScript scripts); Rust toolchain (`cargo build` on skeleton).

---

### Task 1: Project Setup

**Files:**
- Create: `package.json`
- Create: `phase_a_scripts/tsconfig.json`
- Create: `oxidant.config.json`
- Create: `tests/fixtures/simple.ts`
- Create: `tests/fixtures/simple_tsconfig.json`

- [ ] **Step 1: Create `package.json` at repo root**

```json
{
  "name": "oxidant-scripts",
  "private": true,
  "scripts": {
    "extract": "tsx phase_a_scripts/extract_ast.ts",
    "idioms": "tsx phase_a_scripts/detect_idioms.ts"
  },
  "devDependencies": {
    "tsx": "^4.19.0",
    "ts-morph": "^24.0.0",
    "typescript": "^5.7.0"
  }
}
```

- [ ] **Step 2: Create `phase_a_scripts/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "moduleResolution": "node",
    "esModuleInterop": true,
    "strict": true,
    "skipLibCheck": true
  }
}
```

- [ ] **Step 3: Create `oxidant.config.json` at repo root**

```json
{
  "source_repo": "corpora/msagljs",
  "target_repo": "corpora/msagl-rs",
  "source_language": "typescript",
  "target_language": "rust",
  "tsconfig": "corpora/msagljs/tsconfig.json",
  "architectural_decisions": {
    "graph_ownership_strategy": "arena_slotmap",
    "error_handling": "thiserror"
  },
  "crate_inventory": [
    "slotmap",
    "petgraph",
    "nalgebra",
    "thiserror",
    "itertools",
    "ordered-float",
    "serde",
    "serde_json"
  ],
  "model_tiers": {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6"
  },
  "max_attempts": {
    "haiku": 3,
    "sonnet": 4,
    "opus": 5
  },
  "parallelism": 4,
  "subscription_auth": true
}
```

- [ ] **Step 4: Create test fixture `tests/fixtures/simple.ts`**

```typescript
export class Point {
  x: number;
  y: number;

  constructor(x: number, y: number) {
    this.x = x;
    this.y = y;
  }

  add(other: Point): Point {
    return new Point(this.x + other.x, this.y + other.y);
  }

  scale(factor: number): Point {
    return new Point(this.x * factor, this.y * factor);
  }

  isZero(): boolean {
    return this.x === 0 && this.y === 0;
  }
}

export interface Shape {
  area(): number;
  perimeter(): number;
}

export enum Color {
  Red = "RED",
  Green = "GREEN",
  Blue = "BLUE",
}

export function distance(a: Point, b: Point): number {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return Math.sqrt(dx * dx + dy * dy);
}

export function clamp(value: number, min: number, max: number): number {
  if (value < min) return min;
  if (value > max) return max;
  return value;
}
```

- [ ] **Step 5: Create `tests/fixtures/simple_tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "strict": true,
    "skipLibCheck": true
  },
  "include": ["simple.ts"]
}
```

- [ ] **Step 6: Install Node dependencies**

```bash
npm install
```

Expected: `node_modules/` created, `tsx` and `ts-morph` available.

- [ ] **Step 7: Verify Python environment**

```bash
uv sync
```

Expected: `.venv/` created with all packages from `pyproject.toml`.

- [ ] **Step 8: Verify Rust toolchain**

```bash
cargo --version
```

Expected: `cargo 1.x.x` — any recent stable version.

- [ ] **Step 9: Commit**

```bash
git add package.json package-lock.json phase_a_scripts/tsconfig.json oxidant.config.json tests/fixtures/
git commit -m "chore: project setup for Phase A (tsx, ts-morph, config, test fixtures)"
```

---

### Task 2: Manifest Schema

**Files:**
- Create: `src/oxidant/models/manifest.py`
- Create: `tests/test_manifest.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_manifest.py`:

```python
import pytest
from pathlib import Path
from oxidant.models.manifest import (
    ConversionNode, Manifest, NodeKind, NodeStatus, TranslationTier
)


def test_node_roundtrip():
    node = ConversionNode(
        node_id="simple__Point__add",
        source_file="simple.ts",
        line_start=8,
        line_end=10,
        source_text="add(other: Point): Point { return new Point(this.x + other.x, this.y + other.y); }",
        node_kind=NodeKind.METHOD,
        parameter_types={"other": "Point"},
        return_type="Point",
        type_dependencies=["simple__Point"],
        call_dependencies=[],
        callers=["simple__distance"],
        parent_class="simple__Point",
    )
    assert node.status == NodeStatus.NOT_STARTED
    assert node.tier is None
    assert node.snippet_path is None
    data = node.model_dump()
    node2 = ConversionNode(**data)
    assert node2.node_id == node.node_id


def test_manifest_eligible_nodes_respects_deps():
    nodes = {
        "mod__A": ConversionNode(
            node_id="mod__A", source_file="a.ts", line_start=1, line_end=5,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type="void",
            type_dependencies=[], call_dependencies=[], callers=["mod__B"],
        ),
        "mod__B": ConversionNode(
            node_id="mod__B", source_file="a.ts", line_start=7, line_end=12,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type="void",
            type_dependencies=[], call_dependencies=["mod__A"], callers=[],
        ),
    }
    manifest = Manifest(source_repo=".", generated_at="2026-04-15", nodes=nodes)
    eligible = manifest.eligible_nodes()
    assert len(eligible) == 1
    assert eligible[0].node_id == "mod__A"


def test_manifest_json_persistence(tmp_path):
    nodes = {
        "mod__foo": ConversionNode(
            node_id="mod__foo", source_file="a.ts", line_start=1, line_end=3,
            source_text="function foo() {}", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type="void",
            type_dependencies=[], call_dependencies=[], callers=[],
        )
    }
    manifest = Manifest(source_repo=".", generated_at="2026-04-15", nodes=nodes)
    path = tmp_path / "manifest.json"
    manifest.save(path)
    loaded = Manifest.load(path)
    assert loaded.nodes["mod__foo"].source_text == "function foo() {}"
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_manifest.py -v
```

Expected: `ImportError` — `manifest.py` doesn't exist.

- [ ] **Step 3: Create `src/oxidant/models/manifest.py`**

```python
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class NodeKind(str, Enum):
    CLASS = "class"
    CONSTRUCTOR = "constructor"
    METHOD = "method"
    GETTER = "getter"
    SETTER = "setter"
    FREE_FUNCTION = "free_function"
    INTERFACE = "interface"
    ENUM = "enum"
    TYPE_ALIAS = "type_alias"


class NodeStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    CONVERTED = "converted"
    FAILED = "failed"
    HUMAN_REVIEW = "human_review"


class TranslationTier(str, Enum):
    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"


class ConversionNode(BaseModel):
    node_id: str
    source_file: str
    line_start: int
    line_end: int
    source_text: str
    node_kind: NodeKind

    parameter_types: dict[str, str] = Field(default_factory=dict)
    return_type: Optional[str] = None

    type_dependencies: list[str] = Field(default_factory=list)
    call_dependencies: list[str] = Field(default_factory=list)
    callers: list[str] = Field(default_factory=list)

    parent_class: Optional[str] = None
    cyclomatic_complexity: int = 1
    idioms_needed: list[str] = Field(default_factory=list)

    topological_order: Optional[int] = None
    bfs_level: Optional[int] = None

    tier: Optional[TranslationTier] = None
    tier_reason: Optional[str] = None

    status: NodeStatus = NodeStatus.NOT_STARTED
    snippet_path: Optional[str] = None
    attempt_count: int = 0
    last_error: Optional[str] = None


class Manifest(BaseModel):
    version: str = "1.0"
    source_repo: str
    generated_at: str
    nodes: dict[str, ConversionNode] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        return cls.model_validate_json(path.read_text())

    def save(self, path: Path) -> None:
        path.write_text(self.model_dump_json(indent=2))

    def eligible_nodes(self) -> list[ConversionNode]:
        """NOT_STARTED nodes whose every dependency is CONVERTED."""
        converted = {
            nid for nid, node in self.nodes.items()
            if node.status == NodeStatus.CONVERTED
        }
        return [
            node for node in self.nodes.values()
            if node.status == NodeStatus.NOT_STARTED
            and all(dep in converted for dep in node.type_dependencies)
            and all(dep in converted for dep in node.call_dependencies)
        ]

    def update_node(self, path: Path, node_id: str, **fields: object) -> None:
        """Update a node's fields and persist the manifest to disk."""
        self.nodes[node_id] = self.nodes[node_id].model_copy(update=fields)
        self.save(path)
```

- [ ] **Step 4: Run to verify pass**

```bash
uv run pytest tests/test_manifest.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/oxidant/models/manifest.py tests/test_manifest.py
git commit -m "feat: manifest schema (ConversionNode, Manifest, NodeKind, NodeStatus)"
```

---

### Task 3: Topological Sort

**Files:**
- Modify: `src/oxidant/models/manifest.py` (add `compute_topology()`)
- Modify: `tests/test_manifest.py` (add topology tests)

- [ ] **Step 1: Add failing topology tests to `tests/test_manifest.py`**

Append:

```python
def test_topological_sort_chain():
    # A → B → C (A has no deps; C depends on B; B depends on A)
    nodes = {
        "m__A": ConversionNode(
            node_id="m__A", source_file="x.ts", line_start=1, line_end=2,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type=None,
            type_dependencies=[], call_dependencies=[], callers=["m__B"],
        ),
        "m__B": ConversionNode(
            node_id="m__B", source_file="x.ts", line_start=3, line_end=4,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type=None,
            type_dependencies=[], call_dependencies=["m__A"], callers=["m__C"],
        ),
        "m__C": ConversionNode(
            node_id="m__C", source_file="x.ts", line_start=5, line_end=6,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type=None,
            type_dependencies=["m__B"], call_dependencies=[], callers=[],
        ),
    }
    manifest = Manifest(source_repo=".", generated_at="2026-04-15", nodes=nodes)
    manifest.compute_topology()
    assert manifest.nodes["m__A"].topological_order == 0
    assert manifest.nodes["m__B"].topological_order == 1
    assert manifest.nodes["m__C"].topological_order == 2
    assert manifest.nodes["m__A"].bfs_level == 0
    assert manifest.nodes["m__B"].bfs_level == 1
    assert manifest.nodes["m__C"].bfs_level == 2


def test_topological_sort_parallel_nodes():
    # A and B are both leaves; C depends on both → A and B are level 0, C is level 1
    nodes = {
        "m__A": ConversionNode(
            node_id="m__A", source_file="x.ts", line_start=1, line_end=2,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type=None,
            type_dependencies=[], call_dependencies=[], callers=["m__C"],
        ),
        "m__B": ConversionNode(
            node_id="m__B", source_file="x.ts", line_start=3, line_end=4,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type=None,
            type_dependencies=[], call_dependencies=[], callers=["m__C"],
        ),
        "m__C": ConversionNode(
            node_id="m__C", source_file="x.ts", line_start=5, line_end=6,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type=None,
            type_dependencies=["m__A", "m__B"], call_dependencies=[], callers=[],
        ),
    }
    manifest = Manifest(source_repo=".", generated_at="2026-04-15", nodes=nodes)
    manifest.compute_topology()
    assert manifest.nodes["m__A"].bfs_level == 0
    assert manifest.nodes["m__B"].bfs_level == 0
    assert manifest.nodes["m__C"].bfs_level == 1


def test_topological_sort_raises_on_cycle():
    nodes = {
        "m__A": ConversionNode(
            node_id="m__A", source_file="x.ts", line_start=1, line_end=2,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type=None,
            type_dependencies=["m__B"], call_dependencies=[], callers=[],
        ),
        "m__B": ConversionNode(
            node_id="m__B", source_file="x.ts", line_start=3, line_end=4,
            source_text="", node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={}, return_type=None,
            type_dependencies=["m__A"], call_dependencies=[], callers=[],
        ),
    }
    manifest = Manifest(source_repo=".", generated_at="2026-04-15", nodes=nodes)
    with pytest.raises(ValueError, match="cycle"):
        manifest.compute_topology()
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_manifest.py::test_topological_sort_chain -v
```

Expected: `AttributeError: 'Manifest' object has no attribute 'compute_topology'`

- [ ] **Step 3: Add `compute_topology()` to `Manifest` in `src/oxidant/models/manifest.py`**

Add this method to the `Manifest` class:

```python
def compute_topology(self) -> None:
    """Kahn's algorithm over the unified dependency graph.

    Sets topological_order and bfs_level on every node.
    Raises ValueError if a cycle is detected.
    Nodes whose dependencies point outside the manifest are treated as leaves.
    """
    from collections import deque

    def deps(node: ConversionNode) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for d in node.type_dependencies + node.call_dependencies:
            if d in self.nodes and d not in seen:
                seen.add(d)
                result.append(d)
        return result

    in_degree: dict[str, int] = {nid: 0 for nid in self.nodes}
    dependents: dict[str, list[str]] = {nid: [] for nid in self.nodes}

    for nid, node in self.nodes.items():
        for dep in deps(node):
            in_degree[nid] += 1
            dependents[dep].append(nid)

    bfs_levels: dict[str, int] = {}
    queue: deque[str] = deque()
    for nid, deg in in_degree.items():
        if deg == 0:
            queue.append(nid)
            bfs_levels[nid] = 0

    order = 0
    while queue:
        nid = queue.popleft()
        node = self.nodes[nid]
        self.nodes[nid] = node.model_copy(update={
            "topological_order": order,
            "bfs_level": bfs_levels[nid],
        })
        order += 1
        for dependent in dependents[nid]:
            in_degree[dependent] -= 1
            bfs_levels[dependent] = max(
                bfs_levels.get(dependent, 0),
                bfs_levels[nid] + 1,
            )
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if order != len(self.nodes):
        remaining = [nid for nid, deg in in_degree.items() if deg > 0]
        raise ValueError(f"Dependency cycle detected involving: {remaining}")
```

- [ ] **Step 4: Run all manifest tests**

```bash
uv run pytest tests/test_manifest.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/oxidant/models/manifest.py tests/test_manifest.py
git commit -m "feat: topological sort on manifest (Kahn's algorithm, bfs_level, cycle detection)"
```

---

### Task 4: AST Extraction Script

**Files:**
- Create: `phase_a_scripts/extract_ast.ts`
- Create: `tests/test_extract_ast.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_extract_ast.py`:

```python
import json
import subprocess
from pathlib import Path

FIXTURE_DIR = Path("tests/fixtures")
FIXTURE_TSCONFIG = FIXTURE_DIR / "simple_tsconfig.json"
SCRIPT = Path("phase_a_scripts/extract_ast.ts")


def run_extract(out_path: Path) -> dict:
    result = subprocess.run(
        ["npx", "tsx", str(SCRIPT),
         "--tsconfig", str(FIXTURE_TSCONFIG),
         "--source-root", str(FIXTURE_DIR),
         "--out", str(out_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"extract_ast.ts failed:\n{result.stderr}"
    return json.loads(out_path.read_text())


def test_extracts_class_node(tmp_path):
    data = run_extract(tmp_path / "manifest.json")
    class_nodes = [nid for nid, n in data["nodes"].items() if n["node_kind"] == "class"]
    assert any("Point" in nid for nid in class_nodes)


def test_extracts_methods(tmp_path):
    data = run_extract(tmp_path / "manifest.json")
    method_nodes = {nid: n for nid, n in data["nodes"].items() if n["node_kind"] == "method"}
    add_node = next((n for nid, n in method_nodes.items() if "add" in nid), None)
    assert add_node is not None
    assert "other" in add_node["parameter_types"]
    assert "Point" in (add_node["return_type"] or "")


def test_extracts_free_function(tmp_path):
    data = run_extract(tmp_path / "manifest.json")
    fn_nodes = {nid for nid, n in data["nodes"].items() if n["node_kind"] == "free_function"}
    assert any("distance" in nid for nid in fn_nodes)


def test_extracts_interface(tmp_path):
    data = run_extract(tmp_path / "manifest.json")
    iface_nodes = [nid for nid, n in data["nodes"].items() if n["node_kind"] == "interface"]
    assert any("Shape" in nid for nid in iface_nodes)


def test_extracts_enum(tmp_path):
    data = run_extract(tmp_path / "manifest.json")
    enum_nodes = [nid for nid, n in data["nodes"].items() if n["node_kind"] == "enum"]
    assert any("Color" in nid for nid in enum_nodes)


def test_parent_class_set_on_methods(tmp_path):
    data = run_extract(tmp_path / "manifest.json")
    add_nodes = [n for nid, n in data["nodes"].items() if "Point" in nid and "add" in nid]
    assert add_nodes
    assert add_nodes[0]["parent_class"] is not None
    assert "Point" in add_nodes[0]["parent_class"]


def test_manifest_has_metadata(tmp_path):
    data = run_extract(tmp_path / "manifest.json")
    assert data["version"] == "1.0"
    assert "generated_at" in data
    assert "source_repo" in data


def test_cyclomatic_complexity_present(tmp_path):
    data = run_extract(tmp_path / "manifest.json")
    # clamp() has 2 if-statements → complexity >= 3
    clamp_node = next((n for nid, n in data["nodes"].items() if "clamp" in nid), None)
    assert clamp_node is not None
    assert clamp_node["cyclomatic_complexity"] >= 3
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_extract_ast.py::test_extracts_class_node -v
```

Expected: script not found.

- [ ] **Step 3: Create `phase_a_scripts/extract_ast.ts`**

```typescript
import {
  Project, SourceFile, Node, SyntaxKind, ts,
} from "ts-morph";
import * as path from "path";
import * as fs from "fs";

// ── CLI args ────────────────────────────────────────────────────────────────

const args = process.argv.slice(2);
function getArg(flag: string): string {
  const idx = args.indexOf(flag);
  if (idx === -1 || idx + 1 >= args.length) throw new Error(`Missing ${flag}`);
  return args[idx + 1];
}
const tsconfigPath = path.resolve(getArg("--tsconfig"));
const sourceRoot   = path.resolve(getArg("--source-root"));
const outPath      = getArg("--out");

// ── Node ID ─────────────────────────────────────────────────────────────────

function fileSlug(sf: SourceFile): string {
  const rel = path.relative(sourceRoot, sf.getFilePath());
  return rel.replace(/\.tsx?$/, "").replace(/[/\\]/g, "__").replace(/[^a-zA-Z0-9_]/g, "_");
}

function nodeId(...parts: string[]): string {
  return parts.join("__").replace(/[^a-zA-Z0-9_]/g, "_");
}

// ── Cyclomatic complexity ────────────────────────────────────────────────────

function complexity(root: Node): number {
  let n = 1;
  root.forEachDescendant((d) => {
    switch (d.getKind()) {
      case SyntaxKind.IfStatement:
      case SyntaxKind.ConditionalExpression:
      case SyntaxKind.CaseClause:
      case SyntaxKind.WhileStatement:
      case SyntaxKind.ForStatement:
      case SyntaxKind.ForInStatement:
      case SyntaxKind.ForOfStatement:
      case SyntaxKind.CatchClause:
        n++; break;
      case SyntaxKind.BinaryExpression: {
        const op = (d as any).getOperatorToken().getKind();
        if (op === SyntaxKind.AmpersandAmpersandToken ||
            op === SyntaxKind.BarBarToken ||
            op === SyntaxKind.QuestionQuestionToken) n++;
        break;
      }
    }
  });
  return n;
}

// ── Type text ────────────────────────────────────────────────────────────────

function typeStr(n: Node): string {
  try {
    return n.getType().getText(n as any, ts.TypeFormatFlags.NoTruncation);
  } catch { return "unknown"; }
}

// ── Main ─────────────────────────────────────────────────────────────────────

const project = new Project({ tsConfigFilePath: tsconfigPath });
const resultNodes: Record<string, any> = {};
// callee → set of callers
const callerMap = new Map<string, Set<string>>();

// Pass 1: index all declaration names → nodeId
const declIndex = new Map<string, string>(); // "filePath::name" or "filePath::class::method" → nodeId

for (const sf of project.getSourceFiles()) {
  const slug = fileSlug(sf);
  const fp   = sf.getFilePath();

  for (const cls of sf.getClasses()) {
    const name = cls.getName(); if (!name) continue;
    declIndex.set(`${fp}::${name}`, nodeId(slug, name));
    for (const m of cls.getMethods())
      declIndex.set(`${fp}::${name}::${m.getName()}`, nodeId(slug, name, m.getName()));
    if (cls.getConstructors().length)
      declIndex.set(`${fp}::${name}::constructor`, nodeId(slug, name, "constructor"));
  }
  for (const fn of sf.getFunctions()) {
    const name = fn.getName(); if (!name) continue;
    declIndex.set(`${fp}::${name}`, nodeId(slug, name));
  }
  for (const iface of sf.getInterfaces())
    declIndex.set(`${fp}::${iface.getName()}`, nodeId(slug, iface.getName()));
  for (const en of sf.getEnums())
    declIndex.set(`${fp}::${en.getName()}`, nodeId(slug, en.getName()));
}

function resolveDepId(sym: any): string | null {
  if (!sym) return null;
  for (const decl of (sym.getDeclarations?.() ?? [])) {
    const fp  = decl.getSourceFile().getFilePath();
    const key = `${fp}::${sym.getName()}`;
    if (declIndex.has(key)) return declIndex.get(key)!;
  }
  return null;
}

function typeDepsOf(root: Node): string[] {
  const out: string[] = [];
  root.forEachDescendant((d) => {
    if (d.getKind() === SyntaxKind.TypeReference) {
      const sym = (d as any).getType().getSymbol();
      const id  = resolveDepId(sym);
      if (id && !out.includes(id)) out.push(id);
    }
  });
  return out;
}

function callDepsOf(root: Node, selfId: string, registerCaller = true): string[] {
  const out: string[] = [];
  root.forEachDescendant((d) => {
    if (d.getKind() !== SyntaxKind.CallExpression) return;
    const sym = (d as any).getExpression().getSymbol?.();
    const id  = resolveDepId(sym);
    if (!id || id === selfId || out.includes(id)) return;
    out.push(id);
    if (registerCaller) {
      if (!callerMap.has(id)) callerMap.set(id, new Set());
      callerMap.get(id)!.add(selfId);
    }
  });
  return out;
}

function baseNode(
  id: string, sf: SourceFile, decl: Node, kind: string, parentClass: string | null = null,
): any {
  return {
    node_id: id,
    source_file: path.relative(sourceRoot, sf.getFilePath()),
    line_start: decl.getStartLineNumber(),
    line_end: decl.getEndLineNumber(),
    source_text: decl.getText(),
    node_kind: kind,
    parameter_types: {},
    return_type: null,
    type_dependencies: [],
    call_dependencies: [],
    callers: [],
    parent_class: parentClass,
    cyclomatic_complexity: 1,
    idioms_needed: [],
    topological_order: null,
    bfs_level: null,
    tier: null,
    tier_reason: null,
    status: "not_started",
    snippet_path: null,
    attempt_count: 0,
    last_error: null,
  };
}

// Pass 2: extract
for (const sf of project.getSourceFiles()) {
  const slug = fileSlug(sf);

  // Classes
  for (const cls of sf.getClasses()) {
    const name = cls.getName(); if (!name) continue;
    const classId = nodeId(slug, name);
    const cn = baseNode(classId, sf, cls, "class");
    cn.type_dependencies = typeDepsOf(cls).filter((id: string) => id !== classId);
    resultNodes[classId] = cn;

    // Constructor
    const ctors = cls.getConstructors();
    if (ctors.length) {
      const ctor   = ctors[0];
      const ctorId = nodeId(slug, name, "constructor");
      const cn2    = baseNode(ctorId, sf, ctor, "constructor", classId);
      for (const p of ctor.getParameters()) cn2.parameter_types[p.getName()] = typeStr(p);
      cn2.return_type        = name;
      cn2.type_dependencies  = typeDepsOf(ctor).filter((id: string) => id !== ctorId);
      cn2.call_dependencies  = callDepsOf(ctor, ctorId);
      cn2.cyclomatic_complexity = complexity(ctor);
      resultNodes[ctorId]    = cn2;
    }

    // Methods
    for (const m of cls.getMethods()) {
      const mId = nodeId(slug, name, m.getName());
      const mn  = baseNode(mId, sf, m, "method", classId);
      for (const p of m.getParameters()) mn.parameter_types[p.getName()] = typeStr(p);
      mn.return_type        = m.getReturnType().getText(m as any, ts.TypeFormatFlags.NoTruncation);
      mn.type_dependencies  = typeDepsOf(m).filter((id: string) => id !== mId);
      mn.call_dependencies  = callDepsOf(m, mId);
      mn.cyclomatic_complexity = complexity(m);
      resultNodes[mId]      = mn;
    }
  }

  // Free functions
  for (const fn of sf.getFunctions()) {
    const name = fn.getName(); if (!name) continue;
    const fnId = nodeId(slug, name);
    const fn2  = baseNode(fnId, sf, fn, "free_function");
    for (const p of fn.getParameters()) fn2.parameter_types[p.getName()] = typeStr(p);
    fn2.return_type        = fn.getReturnType().getText(fn as any, ts.TypeFormatFlags.NoTruncation);
    fn2.type_dependencies  = typeDepsOf(fn).filter((id: string) => id !== fnId);
    fn2.call_dependencies  = callDepsOf(fn, fnId);
    fn2.cyclomatic_complexity = complexity(fn);
    resultNodes[fnId]      = fn2;
  }

  // Interfaces
  for (const iface of sf.getInterfaces()) {
    const id = nodeId(slug, iface.getName());
    const n  = baseNode(id, sf, iface, "interface");
    n.type_dependencies = typeDepsOf(iface).filter((i: string) => i !== id);
    resultNodes[id] = n;
  }

  // Enums
  for (const en of sf.getEnums()) {
    const id = nodeId(slug, en.getName());
    resultNodes[id] = baseNode(id, sf, en, "enum");
  }
}

// Backfill callers
for (const [calleeId, callers] of callerMap.entries()) {
  if (resultNodes[calleeId]) resultNodes[calleeId].callers = Array.from(callers);
}

const manifest = {
  version: "1.0",
  source_repo: sourceRoot,
  generated_at: new Date().toISOString(),
  nodes: resultNodes,
};

fs.writeFileSync(outPath, JSON.stringify(manifest, null, 2));
console.log(`Wrote manifest: ${outPath} (${Object.keys(resultNodes).length} nodes)`);
```

- [ ] **Step 4: Run all extraction tests**

```bash
uv run pytest tests/test_extract_ast.py -v
```

Expected: all 8 tests pass. Common failures to fix:
- Node IDs contain unexpected characters → tighten `nodeId()` sanitiser
- `cyclomatic_complexity` value off-by-one → adjust the branch counting logic

- [ ] **Step 5: Commit**

```bash
git add phase_a_scripts/extract_ast.ts tests/test_extract_ast.py
git commit -m "feat: AST extraction script (ts-morph → conversion_manifest.json)"
```

---

### Task 5: Idiom Detection Script

**Files:**
- Create: `phase_a_scripts/detect_idioms.ts`
- Create: `tests/fixtures/idioms.ts`
- Create: `tests/fixtures/idioms_tsconfig.json`
- Create: `tests/test_detect_idioms.py`

- [ ] **Step 1: Create `tests/fixtures/idioms.ts`**

```typescript
export class Example {
  items: number[];
  name: string | null;

  constructor() {
    this.items = [];
    this.name = null;
  }

  // optional chaining
  getFirstItem(): number | undefined {
    return this.items?.[0];
  }

  // null coalescing (null/undefined duality)
  getName(): string {
    return this.name ?? "default";
  }

  // array method chain
  getDoubled(): number[] {
    return this.items.map(x => x * 2).filter(x => x > 0);
  }

  // closure capturing outer scope
  makeAdder(n: number): (x: number) => number {
    return (x) => x + n;
  }

  // Map usage
  buildIndex(): Map<string, number> {
    const m = new Map<string, number>();
    this.items.forEach((v, i) => m.set(String(i), v));
    return m;
  }
}

// async/await
export async function fetchData(url: string): Promise<string> {
  const response = await fetch(url);
  return response.text();
}
```

- [ ] **Step 2: Create `tests/fixtures/idioms_tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "lib": ["ES2022", "DOM"],
    "strict": true,
    "skipLibCheck": true
  },
  "include": ["idioms.ts"]
}
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_detect_idioms.py`:

```python
import json
import subprocess
from pathlib import Path

FIXTURE_DIR   = Path("tests/fixtures")
EXTRACT       = Path("phase_a_scripts/extract_ast.ts")
DETECT_IDIOMS = Path("phase_a_scripts/detect_idioms.ts")


def run_pipeline(tmp_path: Path, tsconfig: str, source_root: str) -> dict:
    mpath = tmp_path / "manifest.json"
    r1 = subprocess.run(
        ["npx", "tsx", str(EXTRACT),
         "--tsconfig", tsconfig,
         "--source-root", source_root,
         "--out", str(mpath)],
        capture_output=True, text=True,
    )
    assert r1.returncode == 0, r1.stderr
    r2 = subprocess.run(
        ["npx", "tsx", str(DETECT_IDIOMS), "--manifest", str(mpath)],
        capture_output=True, text=True,
    )
    assert r2.returncode == 0, r2.stderr
    return json.loads(mpath.read_text())


def test_optional_chaining_detected(tmp_path):
    data = run_pipeline(tmp_path,
        str(FIXTURE_DIR / "idioms_tsconfig.json"), str(FIXTURE_DIR))
    node = next((n for nid, n in data["nodes"].items() if "getFirstItem" in nid), None)
    assert node and "optional_chaining" in node["idioms_needed"]


def test_null_undefined_detected(tmp_path):
    data = run_pipeline(tmp_path,
        str(FIXTURE_DIR / "idioms_tsconfig.json"), str(FIXTURE_DIR))
    node = next((n for nid, n in data["nodes"].items() if "getName" in nid), None)
    assert node and "null_undefined" in node["idioms_needed"]


def test_array_method_chain_detected(tmp_path):
    data = run_pipeline(tmp_path,
        str(FIXTURE_DIR / "idioms_tsconfig.json"), str(FIXTURE_DIR))
    node = next((n for nid, n in data["nodes"].items() if "getDoubled" in nid), None)
    assert node and "array_method_chain" in node["idioms_needed"]


def test_closure_capture_detected(tmp_path):
    data = run_pipeline(tmp_path,
        str(FIXTURE_DIR / "idioms_tsconfig.json"), str(FIXTURE_DIR))
    node = next((n for nid, n in data["nodes"].items() if "makeAdder" in nid), None)
    assert node and "closure_capture" in node["idioms_needed"]


def test_map_usage_detected(tmp_path):
    data = run_pipeline(tmp_path,
        str(FIXTURE_DIR / "idioms_tsconfig.json"), str(FIXTURE_DIR))
    node = next((n for nid, n in data["nodes"].items() if "buildIndex" in nid), None)
    assert node and "map_usage" in node["idioms_needed"]


def test_async_await_detected(tmp_path):
    data = run_pipeline(tmp_path,
        str(FIXTURE_DIR / "idioms_tsconfig.json"), str(FIXTURE_DIR))
    node = next((n for nid, n in data["nodes"].items() if "fetchData" in nid), None)
    assert node and "async_await" in node["idioms_needed"]
```

- [ ] **Step 4: Run to verify failure**

```bash
uv run pytest tests/test_detect_idioms.py::test_optional_chaining_detected -v
```

Expected: `detect_idioms.ts` not found.

- [ ] **Step 5: Create `phase_a_scripts/detect_idioms.ts`**

```typescript
import { Project, Node, SyntaxKind } from "ts-morph";
import * as fs from "fs";

const args = process.argv.slice(2);
function getArg(flag: string): string {
  const idx = args.indexOf(flag);
  if (idx === -1 || idx + 1 >= args.length) throw new Error(`Missing ${flag}`);
  return args[idx + 1];
}
const manifestPath = getArg("--manifest");
const manifest     = JSON.parse(fs.readFileSync(manifestPath, "utf8"));

const ARRAY_METHODS = new Set(["map","filter","reduce","find","some","every","forEach","flatMap","findIndex"]);

type Detector = (n: Node) => boolean;

const IDIOMS: Record<string, Detector> = {
  optional_chaining: (n) =>
    n.getDescendantsOfKind(SyntaxKind.QuestionDotToken).length > 0,

  null_undefined: (n) =>
    n.getDescendantsOfKind(SyntaxKind.NullKeyword).length > 0 ||
    n.getFullText().includes("undefined") ||
    n.getDescendantsOfKind(SyntaxKind.QuestionQuestionToken).length > 0,

  array_method_chain: (n) =>
    n.getDescendantsOfKind(SyntaxKind.CallExpression).some((call) => {
      const expr = call.getExpression();
      return Node.isPropertyAccessExpression(expr) && ARRAY_METHODS.has(expr.getName());
    }),

  closure_capture: (n) =>
    n.getDescendantsOfKind(SyntaxKind.ArrowFunction).length > 0 ||
    n.getDescendantsOfKind(SyntaxKind.FunctionExpression).length > 0,

  map_usage: (n) =>
    n.getFullText().includes("Map<") || n.getFullText().includes("new Map("),

  set_usage: (n) =>
    n.getFullText().includes("Set<") || n.getFullText().includes("new Set("),

  async_await: (n) =>
    n.getDescendantsOfKind(SyntaxKind.AwaitExpression).length > 0 ||
    n.getFullText().includes("async "),

  class_inheritance: (n) =>
    n.getDescendantsOfKind(SyntaxKind.ExtendsKeyword).length > 0,

  discriminated_union: (n) =>
    n.getDescendantsOfKind(SyntaxKind.UnionType).length > 0,

  number_as_index: (n) => {
    const text = n.getFullText();
    return /\[\s*\w+\s*\]/.test(text) && text.includes("number");
  },

  dynamic_property_access: (n) =>
    n.getDescendantsOfKind(SyntaxKind.ElementAccessExpression).length > 0,

  mutable_shared_state: (n) =>
    n.getDescendantsOfKind(SyntaxKind.BinaryExpression).some((b) => {
      const left = b.getLeft().getFullText().trim();
      return left.includes(".") && b.getOperatorToken().getKind() === SyntaxKind.EqualsToken;
    }),

  generator_function: (n) =>
    n.getDescendantsOfKind(SyntaxKind.YieldExpression).length > 0,

  static_members: (n) =>
    n.getDescendantsOfKind(SyntaxKind.StaticKeyword).length > 0,

  union_type: (n) =>
    n.getDescendantsOfKind(SyntaxKind.UnionType).length > 0,
};

// Build in-memory project, one source file per node
const project = new Project({ useInMemoryFileSystem: true });

for (const [nodeId, node] of Object.entries(manifest.nodes) as [string, any][]) {
  if (!node.source_text) continue;
  project.createSourceFile(`/${nodeId}.ts`, node.source_text, { overwrite: true });
}

for (const [nodeId, node] of Object.entries(manifest.nodes) as [string, any][]) {
  const sf = project.getSourceFile(`/${nodeId}.ts`);
  if (!sf) continue;

  const idioms: string[] = [];
  for (const [name, detect] of Object.entries(IDIOMS)) {
    try { if (detect(sf)) idioms.push(name); } catch { /* skip */ }
  }
  manifest.nodes[nodeId].idioms_needed = idioms;
}

fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
console.log(`Idiom detection complete: ${manifestPath}`);
```

- [ ] **Step 6: Run all idiom tests**

```bash
uv run pytest tests/test_detect_idioms.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 7: Commit**

```bash
git add phase_a_scripts/detect_idioms.ts tests/test_detect_idioms.py tests/fixtures/idioms.ts tests/fixtures/idioms_tsconfig.json
git commit -m "feat: idiom detection script (15 TS patterns annotated into manifest)"
```

---

### Task 6: Tier Classification

**Files:**
- Create: `src/oxidant/analysis/__init__.py`
- Create: `src/oxidant/analysis/classify_tiers.py`
- Create: `tests/test_classify_tiers.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_classify_tiers.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from oxidant.models.manifest import ConversionNode, Manifest, NodeKind, TranslationTier
from oxidant.analysis.classify_tiers import classify_manifest


def _node(node_id: str, complexity: int = 1, idioms: list[str] | None = None) -> ConversionNode:
    return ConversionNode(
        node_id=node_id, source_file="x.ts", line_start=1, line_end=5,
        source_text="function foo() { return 1; }",
        node_kind=NodeKind.FREE_FUNCTION,
        parameter_types={}, return_type="number",
        type_dependencies=[], call_dependencies=[], callers=[],
        cyclomatic_complexity=complexity,
        idioms_needed=idioms or [],
    )


def _manifest(nodes: dict) -> Manifest:
    return Manifest(source_repo=".", generated_at="2026-04-15", nodes=nodes)


@patch("oxidant.analysis.classify_tiers.anthropic.Anthropic")
def test_simple_node_classified_haiku(mock_cls, tmp_path):
    mock_cls.return_value.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"tier": "haiku", "reason": "simple getter"}')]
    )
    m = _manifest({"x__foo": _node("x__foo", complexity=1)})
    p = tmp_path / "manifest.json"
    m.save(p)
    classify_manifest(p, model="claude-haiku-4-5-20251001")
    assert Manifest.load(p).nodes["x__foo"].tier == TranslationTier.HAIKU


@patch("oxidant.analysis.classify_tiers.anthropic.Anthropic")
def test_complex_node_classified_opus(mock_cls, tmp_path):
    mock_cls.return_value.messages.create.return_value = MagicMock(
        content=[MagicMock(text='{"tier": "opus", "reason": "cyclic references"}')]
    )
    m = _manifest({"x__hard": _node("x__hard", complexity=20,
                                    idioms=["class_inheritance", "mutable_shared_state", "closure_capture"])})
    p = tmp_path / "manifest.json"
    m.save(p)
    classify_manifest(p, model="claude-haiku-4-5-20251001")
    result = Manifest.load(p).nodes["x__hard"]
    assert result.tier == TranslationTier.OPUS
    assert result.tier_reason


@patch("oxidant.analysis.classify_tiers.anthropic.Anthropic")
def test_invalid_json_falls_back_to_sonnet(mock_cls, tmp_path):
    mock_cls.return_value.messages.create.return_value = MagicMock(
        content=[MagicMock(text="not json")]
    )
    m = _manifest({"x__foo": _node("x__foo")})
    p = tmp_path / "manifest.json"
    m.save(p)
    classify_manifest(p, model="claude-haiku-4-5-20251001")
    assert Manifest.load(p).nodes["x__foo"].tier == TranslationTier.SONNET
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_classify_tiers.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `src/oxidant/analysis/__init__.py`** (empty)

- [ ] **Step 4: Create `src/oxidant/analysis/classify_tiers.py`**

```python
"""Classify each manifest node into a translation tier using Claude Haiku."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import anthropic

from oxidant.models.manifest import Manifest, TranslationTier

logger = logging.getLogger(__name__)

_SYSTEM = """You are a TypeScript-to-Rust translation difficulty classifier.

Tiers:
- haiku: simple getters/setters, basic type definitions, pure arithmetic, no complex idioms
- sonnet: moderate complexity, async conversions, 1-3 complex idioms, non-trivial ownership
- opus: complex algorithms where a wrong simplified version is plausible, cyclic references,
        heavy generics, 4+ complex idioms, deep Rust ownership reasoning required

Respond with ONLY valid JSON on one line: {"tier": "haiku"|"sonnet"|"opus", "reason": "..."}"""

_USER = """\
Node ID: {node_id}
Kind: {node_kind}
Cyclomatic complexity: {complexity}
Idioms: {idioms}

```typescript
{source_text}
```"""


def classify_manifest(manifest_path: Path, model: str) -> None:
    """Classify all untiered nodes in the manifest. Saves after each node."""
    manifest = Manifest.load(manifest_path)
    client = anthropic.Anthropic()

    for node_id, node in manifest.nodes.items():
        if node.tier is not None:
            continue

        prompt = _USER.format(
            node_id=node_id,
            node_kind=node.node_kind.value,
            complexity=node.cyclomatic_complexity,
            idioms=", ".join(node.idioms_needed) or "none",
            source_text=node.source_text[:2000],
        )
        try:
            resp = client.messages.create(
                model=model, max_tokens=128, system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            data = json.loads(resp.content[0].text.strip())
            tier   = TranslationTier(data["tier"])
            reason = data.get("reason", "")
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("classify failed for %s (%s) — defaulting to sonnet", node_id, exc)
            tier, reason = TranslationTier.SONNET, f"parse error: {exc}"

        manifest.nodes[node_id] = node.model_copy(update={"tier": tier, "tier_reason": reason})
        logger.info("%-60s → %s", node_id, tier.value)

    manifest.save(manifest_path)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_classify_tiers.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/oxidant/analysis/__init__.py src/oxidant/analysis/classify_tiers.py tests/test_classify_tiers.py
git commit -m "feat: tier classification (Haiku API call per node, sonnet fallback on error)"
```

---

### Task 7: Skeleton Generator

**Files:**
- Create: `src/oxidant/analysis/generate_skeleton.py`
- Create: `tests/test_generate_skeleton.py`

Type mapping rules used throughout this task:

| TypeScript | Rust |
|---|---|
| `number` | `f64` |
| `string` | `String` |
| `boolean` | `bool` |
| `void` / `undefined` | `()` |
| `T[]` / `Array<T>` | `Vec<T>` |
| `T \| null` / `T \| undefined` | `Option<T>` |
| `Map<K,V>` | `std::collections::HashMap<K,V>` |
| `Set<T>` | `std::collections::HashSet<T>` |
| `any` / `unknown` | `serde_json::Value` |
| Known class `Foo` | `Rc<RefCell<Foo>>` |
| Generic `T` (single capital letter+) | `T` (pass through) |

- [ ] **Step 1: Write failing tests**

Create `tests/test_generate_skeleton.py`:

```python
import subprocess
from pathlib import Path

import pytest

from oxidant.models.manifest import ConversionNode, Manifest, NodeKind, TranslationTier
from oxidant.analysis.generate_skeleton import map_ts_type, generate_skeleton


# ── Type mapper unit tests ────────────────────────────────────────────────────

def test_map_number():      assert map_ts_type("number") == "f64"
def test_map_string():      assert map_ts_type("string") == "String"
def test_map_bool():        assert map_ts_type("boolean") == "bool"
def test_map_void():        assert map_ts_type("void") == "()"
def test_map_array():       assert map_ts_type("number[]") == "Vec<f64>"
def test_map_generic_array(): assert map_ts_type("Array<string>") == "Vec<String>"
def test_map_nullable():
    assert map_ts_type("string | null") == "Option<String>"
    assert map_ts_type("number | undefined") == "Option<f64>"
def test_map_unknown_class():
    assert map_ts_type("Point") == "Rc<RefCell<Point>>"
def test_map_map_type():
    assert map_ts_type("Map<string, number>") == "std::collections::HashMap<String, f64>"


# ── Integration: generated skeleton must compile ──────────────────────────────

def _make_manifest() -> Manifest:
    nodes = {
        "simple__Point": ConversionNode(
            node_id="simple__Point", source_file="simple.ts",
            line_start=1, line_end=20, source_text="class Point {}",
            node_kind=NodeKind.CLASS, parameter_types={}, return_type=None,
            type_dependencies=[], call_dependencies=[], callers=[],
            tier=TranslationTier.HAIKU,
        ),
        "simple__Point__constructor": ConversionNode(
            node_id="simple__Point__constructor", source_file="simple.ts",
            line_start=3, line_end=6,
            source_text="constructor(x: number, y: number) {}",
            node_kind=NodeKind.CONSTRUCTOR,
            parameter_types={"x": "number", "y": "number"}, return_type="Point",
            type_dependencies=["simple__Point"], call_dependencies=[], callers=[],
            parent_class="simple__Point", tier=TranslationTier.HAIKU,
        ),
        "simple__Point__add": ConversionNode(
            node_id="simple__Point__add", source_file="simple.ts",
            line_start=8, line_end=10,
            source_text="add(other: Point): Point { return new Point(0,0); }",
            node_kind=NodeKind.METHOD,
            parameter_types={"other": "Point"}, return_type="Point",
            type_dependencies=["simple__Point"], call_dependencies=[],
            callers=[], parent_class="simple__Point", tier=TranslationTier.HAIKU,
        ),
        "simple__Color": ConversionNode(
            node_id="simple__Color", source_file="simple.ts",
            line_start=25, line_end=29, source_text='enum Color { Red = "RED" }',
            node_kind=NodeKind.ENUM, parameter_types={}, return_type=None,
            type_dependencies=[], call_dependencies=[], callers=[],
            tier=TranslationTier.HAIKU,
        ),
        "simple__distance": ConversionNode(
            node_id="simple__distance", source_file="simple.ts",
            line_start=32, line_end=37,
            source_text="function distance(a: Point, b: Point): number { return 0; }",
            node_kind=NodeKind.FREE_FUNCTION,
            parameter_types={"a": "Point", "b": "Point"}, return_type="number",
            type_dependencies=["simple__Point"], call_dependencies=[], callers=[],
            tier=TranslationTier.HAIKU,
        ),
    }
    return Manifest(source_repo="tests/fixtures", generated_at="2026-04-15", nodes=nodes)


def test_cargo_build_passes(tmp_path):
    manifest = _make_manifest()
    mpath = tmp_path / "manifest.json"
    manifest.save(mpath)
    target = tmp_path / "msagl-rs"
    generate_skeleton(mpath, target)
    r = subprocess.run(["cargo", "build"], cwd=target, capture_output=True, text=True)
    assert r.returncode == 0, f"cargo build failed:\n{r.stderr}"


def test_todo_markers_present(tmp_path):
    manifest = _make_manifest()
    mpath = tmp_path / "manifest.json"
    manifest.save(mpath)
    target = tmp_path / "msagl-rs"
    generate_skeleton(mpath, target)
    all_rs = "\n".join(f.read_text() for f in target.rglob("*.rs"))
    assert "OXIDANT" in all_rs
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_generate_skeleton.py::test_map_number -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `src/oxidant/analysis/generate_skeleton.py`**

```python
"""Generate a compilable Rust skeleton from conversion_manifest.json.

Every function body is `todo!("OXIDANT: …")`. Must pass `cargo build`.
Phase B replaces the stubs one node at a time.
"""

from __future__ import annotations

import re
import textwrap
from collections import defaultdict
from pathlib import Path

from oxidant.models.manifest import ConversionNode, Manifest, NodeKind

# TypeScript built-ins → Rust
_PRIMITIVES: dict[str, str] = {
    "number": "f64", "string": "String", "boolean": "bool",
    "void": "()", "undefined": "()", "null": "()",
    "never": "!", "any": "serde_json::Value", "unknown": "serde_json::Value",
    "object": "serde_json::Value",
}


def map_ts_type(ts_type: str, known_classes: set[str] | None = None) -> str:
    """Map a TypeScript type string to a Rust type string."""
    t = ts_type.strip()
    known = known_classes or set()

    if t in _PRIMITIVES:
        return _PRIMITIVES[t]

    # T[]
    if t.endswith("[]"):
        return f"Vec<{map_ts_type(t[:-2], known)}>"

    # Array<T>
    if m := re.fullmatch(r"Array<(.+)>", t):
        return f"Vec<{map_ts_type(m.group(1), known)}>"

    # T | null / T | undefined
    parts = [p.strip() for p in t.split("|")]
    non_null = [p for p in parts if p not in ("null", "undefined")]
    if len(non_null) < len(parts):
        if len(non_null) == 1:
            return f"Option<{map_ts_type(non_null[0], known)}>"
        return "Option<serde_json::Value>"

    # Map<K, V>
    if m := re.fullmatch(r"Map<(.+?),\s*(.+)>", t):
        return f"std::collections::HashMap<{map_ts_type(m.group(1), known)}, {map_ts_type(m.group(2), known)}>"

    # Set<T>
    if m := re.fullmatch(r"Set<(.+)>", t):
        return f"std::collections::HashSet<{map_ts_type(m.group(1), known)}>"

    # Promise<T>
    if m := re.fullmatch(r"Promise<(.+)>", t):
        return f"impl std::future::Future<Output = {map_ts_type(m.group(1), known)}>"

    # Generic type parameter (single capital or all caps)
    if re.fullmatch(r"[A-Z][A-Z0-9]*", t):
        return t

    # Known or guessed class → Rc<RefCell<Foo>>
    if t in known or re.fullmatch(r"[A-Z][a-zA-Z0-9]*", t):
        return f"Rc<RefCell<{t}>>"

    return "serde_json::Value"


def _to_snake(name: str) -> str:
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower()


def _module_name(source_file: str) -> str:
    stem = Path(source_file).stem
    return re.sub(r"[^a-z0-9_]", "_", _to_snake(stem))


def _struct_name(node_id: str) -> str:
    return node_id.split("__")[-1]


def generate_skeleton(manifest_path: Path, target_path: Path) -> None:
    """Write a compilable Rust project to target_path."""
    manifest = Manifest.load(manifest_path)
    target_path.mkdir(parents=True, exist_ok=True)

    known_classes = {
        _struct_name(nid)
        for nid, n in manifest.nodes.items()
        if n.node_kind == NodeKind.CLASS
    }

    def t(ts: str | None) -> str:
        return map_ts_type(ts or "void", known_classes)

    by_module: dict[str, list[ConversionNode]] = defaultdict(list)
    for node in manifest.nodes.values():
        by_module[_module_name(node.source_file)].append(node)

    modules = sorted(by_module)
    src = target_path / "src"
    src.mkdir(exist_ok=True)

    # Cargo.toml
    (target_path / "Cargo.toml").write_text(textwrap.dedent("""\
        [package]
        name = "msagl-rs"
        version = "0.1.0"
        edition = "2021"

        [dependencies]
        slotmap      = "1"
        petgraph     = "0.6"
        nalgebra     = "0.33"
        thiserror    = "2"
        itertools    = "0.13"
        ordered-float = "4"
        serde        = { version = "1", features = ["derive"] }
        serde_json   = "1"
    """))

    # lib.rs
    lib_lines = [
        "#![allow(dead_code, unused_variables, unused_imports, non_snake_case)]",
        "use std::rc::Rc;",
        "use std::cell::RefCell;",
        "",
    ]
    for mod_name in modules:
        lib_lines.append(f"pub mod {mod_name};")
    (src / "lib.rs").write_text("\n".join(lib_lines) + "\n")

    # One .rs file per module
    for mod_name, nodes in by_module.items():
        lines: list[str] = [
            "#![allow(dead_code, unused_variables, unused_imports, non_snake_case)]",
            "use std::rc::Rc;",
            "use std::cell::RefCell;",
            "use std::collections::{HashMap, HashSet};",
            "",
        ]

        # Enums
        for node in nodes:
            if node.node_kind != NodeKind.ENUM:
                continue
            name = _struct_name(node.node_id)
            lines += [
                "#[derive(Debug, Clone, PartialEq)]",
                f"pub enum {name} {{",
                "    _Placeholder, // OXIDANT: enum variants not yet translated",
                "}",
                "",
            ]

        # Interfaces → traits
        for node in nodes:
            if node.node_kind != NodeKind.INTERFACE:
                continue
            name = _struct_name(node.node_id)
            lines += [
                f"pub trait {name} {{",
                "    // OXIDANT: trait methods not yet translated",
                "}",
                "",
            ]

        # Classes → structs + impl
        methods_by_class: dict[str, list[ConversionNode]] = defaultdict(list)
        for node in nodes:
            if node.node_kind == NodeKind.METHOD and node.parent_class:
                methods_by_class[node.parent_class].append(node)

        for node in nodes:
            if node.node_kind != NodeKind.CLASS:
                continue
            sname = _struct_name(node.node_id)
            lines += [
                "#[derive(Debug, Clone)]",
                f"pub struct {sname} {{",
                "    _placeholder: (), // OXIDANT: fields not yet translated",
                "}",
                "",
                f"impl {sname} {{",
            ]

            # Constructor
            ctor_id = f"{node.node_id}__constructor"
            if ctor_id in manifest.nodes:
                ctor = manifest.nodes[ctor_id]
                params = ", ".join(f"{k}: {t(v)}" for k, v in ctor.parameter_types.items())
                lines += [
                    f"    pub fn new({params}) -> Self {{",
                    f'        todo!("OXIDANT: not yet translated — {ctor_id}")',
                    "    }",
                    "",
                ]

            # Methods
            for m in methods_by_class.get(node.node_id, []):
                mname = _to_snake(m.node_id.split("__")[-1])
                params = ", ".join(f"{k}: {t(v)}" for k, v in m.parameter_types.items())
                ret = t(m.return_type)
                ret_str = f" -> {ret}" if ret != "()" else ""
                lines += [
                    f"    pub fn {mname}(&self, {params}){ret_str} {{",
                    f'        todo!("OXIDANT: not yet translated — {m.node_id}")',
                    "    }",
                    "",
                ]

            lines += ["}", ""]

        # Free functions
        for node in nodes:
            if node.node_kind != NodeKind.FREE_FUNCTION:
                continue
            fname = _to_snake(node.node_id.split("__")[-1])
            params = ", ".join(f"{k}: {t(v)}" for k, v in node.parameter_types.items())
            ret = t(node.return_type)
            ret_str = f" -> {ret}" if ret != "()" else ""
            lines += [
                f"pub fn {fname}({params}){ret_str} {{",
                f'    todo!("OXIDANT: not yet translated — {node.node_id}")',
                "}",
                "",
            ]

        (src / f"{mod_name}.rs").write_text("\n".join(lines) + "\n")
```

- [ ] **Step 4: Run type-mapper unit tests**

```bash
uv run pytest tests/test_generate_skeleton.py -k "test_map" -v
```

Expected: all 9 pass.

- [ ] **Step 5: Run cargo build integration test**

```bash
uv run pytest tests/test_generate_skeleton.py::test_cargo_build_passes -v
```

Expected: PASS. If `cargo build` fails, read `r.stderr` in the failure output and fix the offending generated Rust. Common issues: invalid identifier (Rust keyword used as name), missing `use` statement.

- [ ] **Step 6: Run full skeleton test suite**

```bash
uv run pytest tests/test_generate_skeleton.py -v
```

Expected: all 11 tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/oxidant/analysis/generate_skeleton.py tests/test_generate_skeleton.py
git commit -m "feat: skeleton generator (manifest → compilable Rust with todo!() stubs)"
```

---

### Task 8: CLI Wiring and End-to-End Smoke Test

**Files:**
- Modify: `src/oxidant/cli.py`
- Create: `tests/test_cli_phase_a.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_phase_a.py`:

```python
import json
import subprocess
from pathlib import Path


def test_phase_a_smoke(tmp_path):
    """Run `oxidant phase-a` against the simple fixture; verify manifest + skeleton."""
    config = {
        "source_repo": str(Path("tests/fixtures")),
        "target_repo": str(tmp_path / "output-rs"),
        "source_language": "typescript",
        "target_language": "rust",
        "tsconfig": str(Path("tests/fixtures/simple_tsconfig.json")),
        "architectural_decisions": {
            "graph_ownership_strategy": "arena_slotmap",
            "error_handling": "thiserror",
        },
        "crate_inventory": ["thiserror", "serde", "serde_json"],
        "model_tiers": {
            "haiku": "claude-haiku-4-5-20251001",
            "sonnet": "claude-sonnet-4-6",
            "opus": "claude-opus-4-6",
        },
        "max_attempts": {"haiku": 3, "sonnet": 4, "opus": 5},
        "parallelism": 1,
        "subscription_auth": True,
    }
    config_path = tmp_path / "oxidant.config.json"
    config_path.write_text(json.dumps(config))
    manifest_path = tmp_path / "manifest.json"

    result = subprocess.run(
        [
            "uv", "run", "oxidant", "phase-a",
            "--config", str(config_path),
            "--manifest-out", str(manifest_path),
            "--skip-tiers",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"phase-a failed:\n{result.stderr}\n{result.stdout}"

    assert manifest_path.exists(), "manifest.json not written"
    data = json.loads(manifest_path.read_text())
    assert len(data["nodes"]) > 0, "manifest has no nodes"

    rs_dir = tmp_path / "output-rs"
    assert (rs_dir / "Cargo.toml").exists(), "Cargo.toml not generated"
    assert (rs_dir / "src" / "lib.rs").exists(), "lib.rs not generated"
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_cli_phase_a.py -v
```

Expected: `UsageError` or `Error: No such command 'phase-a'`.

- [ ] **Step 3: Replace `src/oxidant/cli.py`**

```python
"""Oxidant CLI entry point."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import typer

app = typer.Typer(name="oxidant", help="Agentic TypeScript-to-Rust translation harness.",
                   no_args_is_help=True)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

_SCRIPTS_DIR = Path(__file__).parent.parent.parent / "phase_a_scripts"


@app.command("phase-a")
def phase_a(
    config: Path = typer.Option("oxidant.config.json", "--config", "-c"),
    manifest_out: Path = typer.Option("conversion_manifest.json", "--manifest-out"),
    skip_tiers: bool = typer.Option(False, "--skip-tiers",
                                     help="Skip Haiku tier classification (no API call)"),
) -> None:
    """Run the full Phase A analysis pipeline.

    Steps: A1 extract AST → A2 detect idioms → A3 topology → A4 classify tiers → A5 skeleton.
    """
    cfg = json.loads(config.read_text())
    tsconfig    = cfg["tsconfig"]
    source_root = cfg["source_repo"]
    target_repo = Path(cfg["target_repo"])
    model       = cfg["model_tiers"]["haiku"]

    # A1: AST extraction
    typer.echo("A1: extracting AST...")
    subprocess.run(
        ["npx", "tsx", str(_SCRIPTS_DIR / "extract_ast.ts"),
         "--tsconfig", tsconfig,
         "--source-root", source_root,
         "--out", str(manifest_out)],
        check=True,
    )

    # A2: Idiom detection
    typer.echo("A2: detecting idioms...")
    subprocess.run(
        ["npx", "tsx", str(_SCRIPTS_DIR / "detect_idioms.ts"),
         "--manifest", str(manifest_out)],
        check=True,
    )

    # A3: Topological sort
    typer.echo("A3: computing topological order...")
    from oxidant.models.manifest import Manifest
    manifest = Manifest.load(manifest_out)
    try:
        manifest.compute_topology()
    except ValueError as exc:
        typer.echo(f"Warning: {exc} — continuing without full topology", err=True)
    manifest.save(manifest_out)

    # A4: Tier classification
    if skip_tiers:
        typer.echo("A4: skipped (--skip-tiers)")
    else:
        typer.echo("A4: classifying tiers...")
        from oxidant.analysis.classify_tiers import classify_manifest
        classify_manifest(manifest_out, model=model)

    # A5: Skeleton generation
    typer.echo("A5: generating Rust skeleton...")
    from oxidant.analysis.generate_skeleton import generate_skeleton
    generate_skeleton(manifest_out, target_repo)

    # Verify skeleton compiles
    typer.echo("Verifying skeleton compiles...")
    r = subprocess.run(["cargo", "build"], cwd=target_repo, capture_output=True, text=True)
    if r.returncode != 0:
        typer.echo(f"cargo build FAILED:\n{r.stderr}", err=True)
        raise typer.Exit(1)
    typer.echo("Phase A complete. Skeleton compiles.")

    # Remind about A3 (idiom dictionary — human step)
    typer.echo("\nNext step (manual): review idiom_candidates.json and generate idiom_dictionary.md")
    typer.echo("  Run a single Opus call with the detected patterns as input.")


@app.command()
def translate(
    source: str = typer.Argument(..., help="Path to a .ts file"),
    out: str = typer.Option("output/", "--out", "-o"),
) -> None:
    """Translate TypeScript to Rust (Phase B — not yet implemented)."""
    typer.echo("Phase B not yet implemented.")
    raise typer.Exit(1)


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run the smoke test**

```bash
uv run pytest tests/test_cli_phase_a.py -v
```

Expected: PASS.

- [ ] **Step 5: Run the full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests pass. Fix any regressions.

- [ ] **Step 6: Run Phase A against msagljs**

```bash
uv run oxidant phase-a --skip-tiers
```

Expected output:
```
A1: extracting AST...
Wrote manifest: conversion_manifest.json (NNN nodes)
A2: detecting idioms...
A3: computing topological order...
A4: skipped (--skip-tiers)
A5: generating Rust skeleton...
Verifying skeleton compiles...
Phase A complete. Skeleton compiles.
```

Fix any issues. The most likely failure is `cargo build` on the msagljs skeleton — the type mapper or module structure will need adjustment for the real codebase. Read `cargo build`'s stderr and fix `generate_skeleton.py` accordingly.

- [ ] **Step 7: Commit**

```bash
git add src/oxidant/cli.py tests/test_cli_phase_a.py conversion_manifest.json
git commit -m "feat: phase-a CLI command — full pipeline from msagljs to compilable Rust skeleton"
```

---

## Self-Review

**Spec coverage:**

| PRD Section | Status |
|---|---|
| A1 AST extraction (all node kinds, types, dep edges) | Task 4 |
| A2 Idiom detection (15 patterns) | Task 5 |
| A3 Idiom dictionary (Opus call, human review) | ⚠️ **Not automated** — this is intentionally a human step. CLI prints a reminder. Add a `gen-idiom-dict` command in a future plan if desired. |
| A4 Tier classification (Haiku per node, sonnet fallback) | Task 6 |
| A5 Crate inventory (human, recorded in config) | Task 1 (`oxidant.config.json`) |
| A6 Skeleton generation (compiles, `todo!()` markers) | Task 7 |
| Topological sort + BFS levels + cycle detection | Task 3 |
| Manifest schema (all fields from PRD §A1) | Task 2 |
| Cyclomatic complexity per node | Task 4 (`complexity()` fn) |
| Manifest save/load/update | Task 2 |
| End-to-end CLI | Task 8 |
| cargo build verification of skeleton | Task 8 step 6 |

**A3 gap:** Intentional. The PRD describes A3 as a single Opus call reviewed by a human before Phase B. It's not a pipeline step the CLI should automate. The CLI prints a reminder after Phase A completes.

**Placeholder scan:** None.

**Type consistency:** `map_ts_type` defined and tested in Task 7, called in Task 7. `Manifest.compute_topology()` defined in Task 3, called in Task 8. `classify_manifest()` defined in Task 6, called in Task 8. All import paths consistent with `src/oxidant/` layout.
